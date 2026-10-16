"""`jbus relay`, run as the unit runs it, against a fake Sous Chef webhook, a fake Home
Assistant for the fallback pager, and a fake `notify-send`, all on 127.0.0.1."""

from __future__ import annotations

import contextlib
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

INBOUND = "inbound-key-for-the-relay"
SOUS_CHEF_KEY = "sous-chef-key-nobody-sees"
GATEKEEPER_KEY = "gatekeeper-key"
HA_TOKEN = "home-assistant-token-nobody-sees"
HA_SERVICE = "mobile_app_test_phone"
NOTIFY_SEND = """#!/bin/sh
printf '%s\\n' "$*" >> "$(dirname "$0")/notified"
"""


def free_port() -> int:
    with socket.socket() as one:
        one.bind(("127.0.0.1", 0))
        return one.getsockname()[1]


class Webhook:
    """A webhook that records each POST it takes. `answer` is the status it gives, and
    `delay` how long it waits first."""

    def __init__(self) -> None:
        self.posts: list[tuple[dict, dict]] = []
        self.paths: list[str] = []
        self.answer, self.delay = 200, 0.0
        hook = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                time.sleep(hook.delay)
                data = self.rfile.read(int(self.headers["Content-Length"]))
                code = hook.answer
                if code == 200:
                    hook.posts.append((dict(self.headers), json.loads(data)))
                    hook.paths.append(self.path)
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.url = f"{self.base}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bodies(self, route: str) -> list[dict]:
        return [body for _, body in self.posts if body["relay"]["route"] == route]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hooks():
    made = [Webhook(), Webhook(), Webhook()]
    yield made
    for hook in made:
        hook.close()


class Relay:
    def __init__(self, env: dict[str, str], state) -> None:
        self.port, self.state = free_port(), state
        self.bin = state.parent / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        (self.bin / "notify-send").write_text(NOTIFY_SEND)
        (self.bin / "notify-send").chmod(0o755)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("RELAY_")},
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "RELAY_PORT": str(self.port),
            "RELAY_STATE": str(state),
            "RELAY_TIMEOUT_SECONDS": "1",
            "RELAY_RETRY_SECONDS": "0.3",
            **env,
        }
        self.process = subprocess.Popen(
            [sys.executable, "-m", "jbus", "relay"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def up(self) -> Relay:
        for _ in range(200):
            if self.process.poll() is not None:
                raise AssertionError(f"the relay ended: {self.process.stdout.read()}")
            with socket.socket() as one:
                if one.connect_ex(("127.0.0.1", self.port)) == 0:
                    return self
            time.sleep(0.02)
        raise AssertionError("the relay did not listen")

    def send(self, body: dict, key: str = INBOUND) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Automation-Key": key},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as answer:
                return answer.status, json.loads(answer.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, {}

    def ack(self, id: str, key: str = INBOUND) -> int:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/ack",
            data=json.dumps({"id": id}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Automation-Key": key},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as answer:
                return answer.status
        except urllib.error.HTTPError as error:
            return error.code

    def notified(self) -> list[str]:
        made = self.bin / "notified"
        return made.read_text().splitlines() if made.exists() else []

    def spooled(self, route: str) -> list[dict]:
        held = []
        for path in sorted((self.state / "spool" / route).glob("*.json")):
            with contextlib.suppress(FileNotFoundError):
                held.append(json.loads(path.read_text()))
        return held

    def stop(self) -> str:
        self.process.terminate()
        said, _ = self.process.communicate(timeout=5)
        return said


def env_for(hooks) -> dict[str, str]:
    sous_chef, gatekeeper, pager = hooks
    return {
        "RELAY_INBOUND_KEY": INBOUND,
        "GROK_WEBHOOK_URL": sous_chef.url,
        "GROK_WEBHOOK_KEY": SOUS_CHEF_KEY,
        "GATEKEEPER_WEBHOOK_URL": gatekeeper.url,
        "GATEKEEPER_WEBHOOK_KEY": GATEKEEPER_KEY,
        "PAGER_HA_URL": pager.base,
        "PAGER_HA_TOKEN": HA_TOKEN,
        "PAGER_HA_SERVICE": HA_SERVICE,
    }


@pytest.fixture
def relay(hooks, tmp_path):
    running = Relay(env_for(hooks), tmp_path / "state").up()
    yield running
    if running.process.poll() is None:
        running.stop()


def until(check, seconds: float = 5.0) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.02)
    assert check()


def event(kind: str, loud: str, slug: str = "alpha") -> dict:
    line = f"{kind} {slug}: something"
    said = f"jstack: {line}"
    return {
        "project": "jstack",
        "slug": slug,
        "event": kind,
        "line": line,
        "loud": loud,
        "say": said,
    }


def body(*events: dict) -> dict:
    return {"kind": "events", "say": [e["say"] for e in events], "events": list(events)}


def test_a_blocking_event_reaches_sous_chef_and_gatekeeper_gets_nothing(relay, hooks):
    sous_chef, gatekeeper, _ = hooks
    gate, quiet = event("gate", "user"), event("merged", "quiet", "beta")

    code, said = relay.send(body(gate, quiet))

    assert code == 202 and said["id"]
    until(lambda: len(sous_chef.bodies("blocking")) == 1 and sous_chef.bodies("everything"))
    ((headers, paged),) = [(h, b) for h, b in sous_chef.posts if b["relay"]["route"] == "blocking"]
    assert paged["events"] == [gate] and paged["say"] == [gate["say"]]
    assert paged["relay"]["id"] == said["id"]
    assert headers["X-Automation-Key"] == SOUS_CHEF_KEY
    assert headers["Authorization"] == f"Bearer {SOUS_CHEF_KEY}"
    (full,) = sous_chef.bodies("everything")
    assert full["events"] == [gate, quiet]
    assert gatekeeper.posts == []


@pytest.mark.parametrize("kind", ["reminder", "refresh"])
def test_a_reminder_or_refresh_blocks_whole(relay, hooks, kind):
    sous_chef, _, _ = hooks
    sent = {"kind": kind, "project": "jstack", "at": "x", "say": "jstack: 1 blocks", "items": []}

    relay.send(sent)

    until(lambda: sous_chef.bodies("blocking"))
    (paged,) = sous_chef.bodies("blocking")
    assert {k: v for k, v in paged.items() if k != "relay"} == sent


def test_a_body_with_nothing_that_blocks_goes_on_the_full_feed_only(relay, hooks):
    sous_chef, _, _ = hooks

    relay.send(body(event("merged", "quiet")))

    until(lambda: sous_chef.bodies("everything"))
    time.sleep(0.3)
    assert sous_chef.bodies("blocking") == []


@pytest.mark.parametrize(
    ("key", "value", "why"),
    [
        ("GROK_WEBHOOK_KEY", "REPLACE_ME", "GROK_WEBHOOK_KEY is REPLACE_ME"),
        ("GROK_WEBHOOK_URL", "https://example.com/REPLACE_ME", "GROK_WEBHOOK_URL is REPLACE_ME"),
        ("GROK_WEBHOOK_URL", "", "GROK_WEBHOOK_URL is empty"),
        ("GROK_WEBHOOK_KEY", None, "GROK_WEBHOOK_KEY is missing"),
        ("RELAY_INBOUND_KEY", None, "RELAY_INBOUND_KEY is missing"),
        ("PAGER_HA_TOKEN", "REPLACE_ME", "PAGER_HA_TOKEN is REPLACE_ME"),
        ("PAGER_HA_URL", None, "PAGER_HA_URL is missing"),
        ("PAGER_HA_SERVICE", "", "PAGER_HA_SERVICE is empty"),
    ],
)
def test_a_target_that_is_not_set_fails_the_start(hooks, tmp_path, key, value, why):
    env = env_for(hooks)
    if value is None:
        del env[key]
    else:
        env[key] = value

    started = Relay(env, tmp_path / "state")
    code = started.process.wait(timeout=10)
    said = started.process.stdout.read()

    assert code == 2
    assert why in said
    assert SOUS_CHEF_KEY not in said and hooks[0].url not in said
    assert HA_TOKEN not in said and hooks[2].base not in said


def test_a_duplicate_id_is_sent_once_also_after_a_restart(hooks, tmp_path):
    sous_chef, _, _ = hooks
    sent = body(event("gate", "user"))
    first = Relay(env_for(hooks), tmp_path / "state").up()

    assert first.send(sent)[0] == 202
    until(lambda: len(sous_chef.posts) == 2)
    assert first.send(sent)[0] == 202
    first.stop()
    again = Relay(env_for(hooks), tmp_path / "state").up()
    assert again.send(sent)[0] == 202
    time.sleep(0.5)
    said = again.stop()

    assert len(sous_chef.bodies("everything")) == 1 and len(sous_chef.bodies("blocking")) == 1
    assert "not sent again" in said


def test_a_body_with_its_own_id_is_sent_once(relay, hooks):
    sous_chef, _, _ = hooks

    relay.send({**body(event("merged", "quiet")), "id": "evt-1"})
    relay.send({**body(event("merged", "quiet", "beta")), "id": "evt-1"})

    until(lambda: sous_chef.bodies("everything"))
    time.sleep(0.3)
    (sent,) = sous_chef.bodies("everything")
    assert sent["relay"]["id"] == "evt-1" and sent["events"][0]["slug"] == "alpha"


def test_a_down_webhook_keeps_the_event_spooled_and_the_next_is_still_taken(relay, hooks):
    sous_chef, _, _ = hooks
    sous_chef.answer = 503
    gate = body(event("gate", "user"))

    code, said = relay.send(gate)

    assert code == 202
    until(lambda: relay.spooled("blocking"))
    time.sleep(0.4)
    assert [b["relay"]["id"] for b in relay.spooled("blocking")] == [said["id"]]
    code, later = relay.send(body(event("stall", "user", "beta")))
    assert code == 202
    assert [b["relay"]["id"] for b in relay.spooled("blocking")] == [said["id"], later["id"]]

    sous_chef.answer = 200
    until(lambda: len(sous_chef.bodies("blocking")) == 2)
    assert [b["relay"]["id"] for b in sous_chef.bodies("blocking")] == [said["id"], later["id"]]
    until(lambda: relay.spooled("blocking") == [])
    log = relay.stop()
    assert f"relay: POST to sous-chef (blocking) failed for event {said['id']}: HTTP 503" in log
    assert SOUS_CHEF_KEY not in log


def test_a_slow_webhook_does_not_hold_back_taking_the_next_event(relay, hooks):
    sous_chef, _, _ = hooks
    sous_chef.delay = 3.0
    relay.send(body(event("gate", "user")))
    time.sleep(0.1)

    start = time.monotonic()
    code, _ = relay.send(body(event("alert", "user", "beta")))

    assert code == 202 and time.monotonic() - start < 0.5
    assert len(relay.spooled("blocking")) == 2
    time.sleep(1.5)
    assert "relay: POST to sous-chef (blocking) failed for event" in relay.stop()


def test_the_wrong_inbound_key_is_refused_and_spools_nothing(relay):
    assert relay.send(body(event("gate", "user")), key="wrong")[0] == 401
    assert relay.spooled("blocking") == [] and relay.spooled("everything") == []


def test_a_body_the_webhook_refuses_is_kept_aside_and_the_next_goes(relay, hooks):
    sous_chef, _, _ = hooks
    sous_chef.answer = 400
    code, refused = relay.send({**body(event("merged", "quiet")), "id": "refused-1"})
    assert code == 202
    dead = relay.state / "dead" / "everything"
    until(lambda: dead.is_dir() and list(dead.glob("*-refused-1.json")))

    sous_chef.answer = 200
    code, later = relay.send(body(event("merged", "quiet", "beta")))

    until(lambda: sous_chef.bodies("everything"))
    assert [b["relay"]["id"] for b in sous_chef.bodies("everything")] == [later["id"]]
    assert "failed for event refused-1: HTTP 400, refused for good" in relay.stop()


def test_a_target_url_that_is_not_http_fails_the_start(hooks, tmp_path):
    env = {**env_for(hooks), "GROK_WEBHOOK_URL": "hooks.example/a-path"}

    started = Relay(env, tmp_path / "state")

    assert started.process.wait(timeout=10) == 2
    assert "GROK_WEBHOOK_URL is not an http or https URL" in started.process.stdout.read()


def test_the_same_body_after_the_dedup_window_is_sent_again(hooks, tmp_path):
    sous_chef, _, _ = hooks
    alert = body(event("alert", "user"))
    running = Relay({**env_for(hooks), "RELAY_DEDUP_SECONDS": "1"}, tmp_path / "state").up()

    running.send(alert)
    until(lambda: len(sous_chef.bodies("blocking")) == 1)
    time.sleep(1.2)
    running.send(alert)

    until(lambda: len(sous_chef.bodies("blocking")) == 2)
    assert len(sous_chef.bodies("everything")) == 2
    running.stop()


@pytest.mark.parametrize("answer", [401, 403, 404])
def test_a_target_that_refuses_the_key_or_the_address_keeps_the_body_to_send_again(
    relay, hooks, answer
):
    sous_chef, _, _ = hooks
    sous_chef.answer = answer

    code, said = relay.send(body(event("gate", "user")))
    assert code == 202
    time.sleep(0.5)
    assert [b["relay"]["id"] for b in relay.spooled("blocking")] == [said["id"]]

    sous_chef.answer = 200
    until(lambda: sous_chef.bodies("blocking"))
    assert not (relay.state / "dead").exists()


def test_a_body_with_its_own_id_is_not_sent_again_after_the_window(hooks, tmp_path):
    sous_chef, _, _ = hooks
    env = {**env_for(hooks), "RELAY_DEDUP_SECONDS": "1"}
    first = Relay(env, tmp_path / "state").up()
    first.send({**body(event("merged", "quiet")), "id": "evt-1"})
    until(lambda: sous_chef.bodies("everything"))
    first.stop()
    time.sleep(1.2)

    again = Relay(env, tmp_path / "state").up()
    again.send({**body(event("merged", "quiet")), "id": "evt-1"})
    time.sleep(0.5)
    said = again.stop()

    assert len(sous_chef.bodies("everything")) == 1
    assert "evt-1 already, not sent again" in said


def test_a_4xx_not_about_the_target_is_kept_aside_and_the_next_goes(relay, hooks):
    sous_chef, _, _ = hooks
    sous_chef.answer = 409
    relay.send({**body(event("gate", "user")), "id": "conflict-1"})
    dead = relay.state / "dead" / "blocking"
    until(lambda: dead.is_dir() and list(dead.glob("*-conflict-1.json")))

    sous_chef.answer = 200
    code, later = relay.send(body(event("stall", "user", "beta")))

    until(lambda: sous_chef.bodies("blocking"))
    assert [b["relay"]["id"] for b in sous_chef.bodies("blocking")] == [later["id"]]


def at(minutes: float) -> str:
    """A time `minutes` after the item began to block, as jbus writes it."""
    return (OPENED + timedelta(minutes=minutes)).isoformat()


OPENED = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def item(key: str = "gate:q33", line: str = "gate 33: tea or coffee?") -> dict:
    return {
        "project": "jstack",
        "key": key,
        "case": "a",
        "why": "a gate with no default",
        "kind": "gate",
        "line": line,
        "since": OPENED.isoformat(),
        "opened": OPENED.isoformat(),
        "url": "https://example.com/pull/1?token=secret",
    }


def second(kind: str, minutes: float, *items: dict) -> dict:
    """A body jbus posts its second target, `minutes` after the items began to block."""
    return {
        "kind": kind,
        "project": "jstack",
        "at": at(minutes),
        "say": [f"jstack: {kind} {one['line']}" for one in items] or ["jstack: nothing blocks"],
        "items": list(items),
    }


def pages(pager) -> list[str]:
    return [body["message"] for _, body in pager.posts]


def test_a_down_sous_chef_pages_once_per_event_with_its_id(relay, hooks):
    sous_chef, _, pager = hooks
    sous_chef.answer = 503

    _, first = relay.send(body(event("gate", "user")))
    _, later = relay.send(body(event("stall", "user", "beta")))
    until(lambda: len(pager.posts) == 2)
    time.sleep(1.0)

    assert sorted(pages(pager)) == sorted(
        [
            f"jstack: gate alpha: something, blocking 0 min, event {first['id']}",
            f"jstack: stall beta: something, blocking 0 min, event {later['id']}",
        ]
    )
    assert pager.paths == [f"/api/services/notify/{HA_SERVICE}"] * 2
    assert all(h["Authorization"] == f"Bearer {HA_TOKEN}" for h, _ in pager.posts)
    assert [set(b) for _, b in pager.posts] == [{"message"}, {"message"}]
    assert sorted(relay.notified()) == sorted(f"-u critical jbus page {m}" for m in pages(pager))
    assert HA_TOKEN not in relay.stop()


def test_a_sous_chef_that_takes_the_page_pages_nothing(relay, hooks):
    sous_chef, _, pager = hooks

    relay.send(body(event("gate", "user")))
    until(lambda: sous_chef.bodies("blocking"))
    time.sleep(0.5)

    assert pager.posts == [] and relay.notified() == []


def test_an_item_open_at_45_minutes_pages_once_and_not_twice(relay, hooks):
    _, _, pager = hooks
    open_ = item()

    relay.send(second("events", 0, open_))
    relay.send(second("reminder", 15, open_))
    relay.send(second("refresh", 44, open_))
    time.sleep(0.5)
    assert pager.posts == []
    relay.send(second("refresh", 45, open_))
    until(lambda: pager.posts)
    relay.send(second("refresh", 105, open_))
    relay.send(second("reminder", 106, open_))
    time.sleep(0.5)

    assert pages(pager) == ["jstack: gate 33: tea or coffee?, blocking 45 min"]
    assert relay.notified() == [
        "-u critical jbus page jstack: gate 33: tea or coffee?, blocking 45 min"
    ]


def test_the_page_is_sent_once_also_after_a_restart(hooks, tmp_path):
    _, _, pager = hooks
    first = Relay(env_for(hooks), tmp_path / "state").up()
    first.send(second("reminder", 15, item()))
    first.send(second("refresh", 50, item()))
    until(lambda: pager.posts)
    first.stop()

    again = Relay(env_for(hooks), tmp_path / "state").up()
    again.send(second("refresh", 110, item()))
    time.sleep(0.5)
    again.stop()

    assert len(pager.posts) == 1


def test_an_item_closed_at_44_minutes_pages_nothing(relay, hooks):
    _, _, pager = hooks
    closing, staying = item(), item("#12", "hand-merge #12: held")

    relay.send(second("reminder", 15, closing, staying))
    relay.send(second("refresh", 44, staying | {"opened": at(30), "since": at(30)}))
    relay.send(second("refresh", 60, staying | {"opened": at(30), "since": at(30)}))
    relay.send(second("refresh", 120))
    time.sleep(0.5)

    assert pager.posts == [] and relay.notified() == []


def test_a_refresh_closes_only_its_own_projects_items(relay, hooks):
    _, _, pager = hooks
    theirs = item() | {"project": "other"}

    relay.send(second("reminder", 15, theirs) | {"project": "other"})
    relay.send(second("refresh", 40))
    relay.send(second("refresh", 60, theirs) | {"project": "other"})

    until(lambda: pager.posts)
    assert pages(pager) == ["other: gate 33: tea or coffee?, blocking 60 min"]


def test_an_acknowledged_item_does_not_page(relay, hooks):
    _, _, pager = hooks
    seen, unseen = item(), item("#12", "hand-merge #12: held")

    code, reminded = relay.send(second("reminder", 15, seen))
    assert relay.ack(reminded["id"]) == 200
    relay.send(second("reminder", 16, unseen))
    relay.send(second("refresh", 60, seen, unseen))

    until(lambda: pager.posts)
    time.sleep(0.5)
    assert pages(pager) == ["jstack: hand-merge #12: held, blocking 60 min"]


def test_an_ack_with_the_wrong_key_or_an_unknown_id_marks_nothing(relay, hooks):
    _, _, pager = hooks
    _, reminded = relay.send(second("reminder", 15, item()))

    assert relay.ack(reminded["id"], key="wrong") == 401
    assert relay.ack("never-sent") == 404
    relay.send(second("refresh", 50, item()))

    until(lambda: pager.posts)
    assert len(pager.posts) == 1


def test_a_page_line_carries_no_url_with_a_token(relay, hooks):
    _, _, pager = hooks
    leaky = item(line="hand-merge #1 https://user:pw@example.com/x?token=abc: held")

    relay.send(second("refresh", 50, leaky))

    until(lambda: pager.posts)
    (said,) = pages(pager)
    assert said == "jstack: hand-merge #1 <url>: held, blocking 50 min"


def test_a_down_pager_keeps_the_page_to_send_again(relay, hooks):
    _, _, pager = hooks
    pager.answer = 503

    relay.send(second("refresh", 50, item()))
    time.sleep(0.5)
    assert pager.posts == [] and len(relay.notified()) == 1
    pager.answer = 200

    until(lambda: pager.posts)
    assert len(pager.posts) == 1 and len(relay.notified()) == 1
