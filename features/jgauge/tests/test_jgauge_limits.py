"""`jgauge limits` reads each Claude account's use ahead of time into the ledger. These tests
run the command itself, as the timer runs it, in a throwaway HOME with two Claude homes, against
a fake usage endpoint that answers each home's token with that account's use."""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent
PRIME = "claudeAgent_claude_prime"
MAIN_ACCOUNT, PRIME_ACCOUNT = "9282d67c-main", "3c536e2a-prime"
FIVE = "2026-10-20T21:29:59.738902+00:00"
WEEK = "2026-10-25T19:59:59.738929+00:00"
FIVE_AT, WEEK_AT = 1792531799, 1792958399


def usage(five, week, five_at=FIVE, week_at=WEEK):
    """An answer in the endpoint's shape, which Claude Code also caches."""
    return {
        "five_hour": {"utilization": five, "resets_at": five_at, "limit_dollars": None},
        "seven_day": {"utilization": week, "resets_at": week_at, "limit_dollars": None},
        "seven_day_opus": None,
    }


class Endpoint:
    """A fake usage endpoint: an answer or a status for each token, and every token the command
    sent it."""

    def __init__(self):
        self.answers = {}
        self.tokens = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                endpoint.tokens.append((token, self.headers.get("anthropic-beta")))
                status, body = endpoint.answers.get(token, (401, {}))
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/oauth/usage"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Machine:
    """A HOME with `~/.claude` and `~/.claude_prime` signed in, the inventory that names them, and
    the ledger under it."""

    def __init__(self, root: Path, endpoint: Endpoint):
        self.home = root / "home"
        self.config = root / "config"
        self.ledger = self.home / ".local" / "state" / "claude" / "limits"
        self.endpoint = endpoint
        (self.config / "jstack").mkdir(parents=True)
        inventory = {
            "claudeAgent": {"driver": "claudeAgent", "enabled": True},
            PRIME: {"driver": "claudeAgent", "config": {"homePath": "~/.claude_prime"}},
            "codex": {"driver": "codex", "enabled": True},
        }
        (self.config / "jstack" / "providers.json").write_text(json.dumps(inventory))
        self.homes = {
            "claudeAgent": (self.home / ".claude", self.home / ".claude.json", MAIN_ACCOUNT),
            PRIME: (
                self.home / ".claude_prime",
                self.home / ".claude_prime" / ".claude.json",
                PRIME_ACCOUNT,
            ),
        }
        for instance in self.homes:
            self.sign_in(instance)

    def file(self, instance):
        return (
            self.ledger
            if instance == "claudeAgent"
            else self.ledger.with_name(f"limits.{instance}")
        )

    def token(self, instance):
        return f"secret-token-of-{instance}"

    def sign_in(self, instance, expires_in=3600):
        home, config, account = self.homes[instance]
        home.mkdir(parents=True, exist_ok=True)
        oauth = {
            "accessToken": self.token(instance),
            "refreshToken": f"refresh-{instance}",
            "expiresAt": int((time.time() + expires_in) * 1000),
        }
        (home / ".credentials.json").write_text(json.dumps({"claudeAiOauth": oauth}))
        config.write_text(json.dumps({"oauthAccount": {"accountUuid": account}}))

    def cache(self, instance, answer, age_seconds=60, account=None):
        _, config, signed_in = self.homes[instance]
        cached = {
            "fetchedAtMs": int((time.time() - age_seconds) * 1000),
            "accountUuid": account or signed_in,
            "utilization": answer,
        }
        config.write_text(
            json.dumps(
                {"oauthAccount": {"accountUuid": signed_in}, "cachedUsageUtilization": cached}
            )
        )

    def answer(self, instance, body, status=200):
        self.endpoint.answers[self.token(instance)] = (status, body)

    def run(self, *more):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("XDG_", "LIMITS", "JGAUGE_"))
        }
        env |= {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config),
            "JGAUGE_USAGE_URL": self.endpoint.url,
        }
        done = subprocess.run(
            [str(BIN / "jgauge"), "limits", *more],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return done.returncode, done.stdout, done.stderr

    def lines(self, instance):
        return self.file(instance).read_text().splitlines()

    def untouched(self):
        """Each credentials file and `.claude.json`, its bytes and its time."""
        files = [
            path
            for home, config, _ in self.homes.values()
            for path in (home / ".credentials.json", config)
        ]
        return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}


@pytest.fixture
def machine(tmp_path):
    endpoint = Endpoint()
    yield Machine(tmp_path, endpoint)
    endpoint.close()


def test_both_ledger_files_get_both_windows_from_each_homes_own_token(machine):
    machine.answer("claudeAgent", usage(42.0, 36.0))
    machine.answer(PRIME, usage(3.5, 0.0, five_at="2026-10-20T21:30:00.310194+00:00"))
    before = machine.untouched()
    code, out, err = machine.run()
    assert (code, err) == (0, "")
    assert machine.lines("claudeAgent") == [f"five_hour 42 {FIVE_AT}", f"seven_day 36 {WEEK_AT}"]
    assert machine.lines(PRIME) == [f"five_hour 3.5 {FIVE_AT + 1}", f"seven_day 0 {WEEK_AT}"]
    assert sorted(machine.endpoint.tokens) == sorted(
        (machine.token(name), "oauth-2025-04-20") for name in ("claudeAgent", PRIME)
    )
    assert out.splitlines() == [
        f"claudeAgent from the endpoint: five_hour 42%, seven_day 36%, into {machine.ledger}",
        f"{PRIME} from the endpoint: five_hour 3.5%, seven_day 0%, into {machine.file(PRIME)}",
    ]
    assert "secret-token" not in out and machine.untouched() == before


def test_a_reset_that_moves_by_a_second_between_calls_does_not_freeze_the_share(machine):
    machine.answer("claudeAgent", usage(42.0, 36.0, five_at="2026-10-20T21:30:00.310194+00:00"))
    machine.answer(PRIME, usage(0.0, 0.0))
    machine.run()
    machine.answer("claudeAgent", usage(47.0, 37.0, five_at="2026-10-20T21:29:59.912000+00:00"))
    machine.run()
    assert machine.lines("claudeAgent") == [
        f"five_hour 47 {FIVE_AT + 1}",
        f"seven_day 37 {WEEK_AT}",
    ]


def test_an_expired_token_falls_back_to_a_fresh_cache_and_is_never_used(machine):
    machine.sign_in("claudeAgent", expires_in=-60)
    machine.cache("claudeAgent", usage(91, 40), age_seconds=5 * 60)
    machine.answer(PRIME, usage(1.0, 2.0))
    before = machine.untouched()
    code, out, _ = machine.run()
    assert code == 0
    assert machine.lines("claudeAgent") == [f"five_hour 91 {FIVE_AT}", f"seven_day 40 {WEEK_AT}"]
    assert out.splitlines()[0].startswith("claudeAgent from the cache: five_hour 91%")
    assert machine.token("claudeAgent") not in [token for token, _ in machine.endpoint.tokens]
    assert machine.untouched() == before


@pytest.mark.parametrize(
    ("age", "account", "why"),
    [
        (16 * 60, None, "its cached usage is 16 min old"),
        (60, "another-account", "its cached usage is of another account"),
    ],
)
def test_a_stale_cache_or_another_accounts_writes_nothing_and_keeps_the_last_line(
    machine, age, account, why
):
    machine.ledger.parent.mkdir(parents=True)
    machine.ledger.write_text(f"five_hour 100 {FIVE_AT}\n")
    os.utime(machine.ledger, (time.time() - 3600,) * 2)
    written = machine.ledger.stat().st_mtime_ns
    machine.sign_in("claudeAgent", expires_in=-60)
    machine.cache("claudeAgent", usage(5, 5), age_seconds=age, account=account)
    machine.answer(PRIME, usage(1.0, 2.0))
    code, out, _ = machine.run()
    assert code == 0
    assert machine.lines("claudeAgent") == [f"five_hour 100 {FIVE_AT}"]
    assert machine.ledger.stat().st_mtime_ns == written
    assert out.splitlines()[0] == (
        "stale claudeAgent: endpoint: its token has expired, and is never refreshed here;"
        f" cache: {why}"
    )


def test_a_500_keeps_the_old_line_and_the_check_then_finds_it_stale(machine):
    machine.answer("claudeAgent", usage(97.0, 50.0))
    machine.answer(PRIME, usage(1.0, 2.0))
    machine.run()
    assert machine.run("--check")[:2] == (0, "")
    os.utime(machine.ledger, (time.time() - 16 * 60,) * 2)
    machine.answer("claudeAgent", {"error": "overloaded"}, status=500)
    code, out, _ = machine.run()
    assert machine.lines("claudeAgent") == [f"five_hour 97 {FIVE_AT}", f"seven_day 50 {WEEK_AT}"]
    assert out.splitlines()[0] == (
        "stale claudeAgent: endpoint: the usage endpoint answered 500;"
        f" cache: {machine.homes['claudeAgent'][1]} has no cached usage"
    )
    code, out, _ = machine.run("--check")
    assert code == 1
    assert out == f"stale claudeAgent: {machine.ledger} was written 16 min ago, 15 min or more\n"


def test_a_window_with_no_reset_is_not_open_and_the_read_still_makes_the_file_fresh(machine):
    machine.answer("claudeAgent", usage(0.0, 0.0, five_at=None, week_at=None))
    machine.answer(PRIME, usage(0.0, 0.0, five_at=None))
    code, out, _ = machine.run()
    assert machine.lines("claudeAgent") == [] and machine.lines(PRIME) == [f"seven_day 0 {WEEK_AT}"]
    assert (
        out.splitlines()[0]
        == f"claudeAgent from the endpoint: no window open, into {machine.ledger}"
    )
    assert machine.run("--check")[:2] == (0, "")


def test_the_check_names_a_declared_instance_with_no_file(machine):
    code, out, _ = machine.run("--check")
    assert code == 1
    assert out.splitlines() == [
        f"stale claudeAgent: no {machine.ledger}",
        f"stale {PRIME}: no {machine.file(PRIME)}",
    ]


def test_with_no_inventory_the_built_in_home_alone_is_read(machine):
    (machine.config / "jstack" / "providers.json").unlink()
    machine.answer("claudeAgent", usage(10.0, 20.0))
    code, out, _ = machine.run()
    assert code == 0 and len(out.splitlines()) == 1
    assert not machine.file(PRIME).exists()


def test_a_reading_merges_by_the_ledgers_rule_and_never_lowers_a_cap_of_the_same_window(machine):
    """jbus wrote a share of 100 percent until the reset. The endpoint's lower share of the
    same window does not replace it."""
    machine.ledger.parent.mkdir(parents=True)
    machine.ledger.write_text(f"five_hour 100 {FIVE_AT}\n")
    machine.answer("claudeAgent", usage(99.0, 36.0))
    machine.answer(PRIME, usage(1.0, 2.0))
    machine.run()
    assert machine.lines("claudeAgent") == [f"five_hour 100 {FIVE_AT}", f"seven_day 36 {WEEK_AT}"]
    assert time.time() - machine.ledger.stat().st_mtime < 60


@pytest.mark.parametrize(
    "given", ["2026-10-20T21:29:59.919173+00:00", "2026-10-20T21:30:00.310194+00:00"]
)
def test_a_cap_another_writer_floored_to_the_second_is_the_same_window_and_stands(machine, given):
    """`hooks/limits.sh` and jbus write a reset to the second, and the endpoint's reset comes a
    second either side of it. The two resets are one window, and the lower share never
    replaces the cap."""
    machine.ledger.parent.mkdir(parents=True)
    machine.ledger.write_text("five_hour 100 1792531799\n")
    machine.answer("claudeAgent", usage(63.0, 36.0, five_at=given))
    machine.answer(PRIME, usage(1.0, 2.0))
    machine.run()
    (five,) = [line for line in machine.lines("claudeAgent") if line.startswith("five_hour")]
    assert five.split()[1] == "100"
