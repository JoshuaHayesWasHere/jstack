"""`jbus relay`, run as the unit runs it, against a fake Sous Chef webhook on 127.0.0.1."""

from __future__ import annotations

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

import pytest

INBOUND = "inbound-key-for-the-relay"
SOUS_CHEF_KEY = "sous-chef-key-nobody-sees"
GATEKEEPER_KEY = "gatekeeper-key"


def free_port() -> int:
    with socket.socket() as one:
        one.bind(("127.0.0.1", 0))
        return one.getsockname()[1]


class Webhook:
    """A webhook that records each POST it takes. `answer` is the status it gives, and
    `delay` how long it waits first."""

    def __init__(self) -> None:
        self.posts: list[tuple[dict, dict]] = []
        self.answer, self.delay = 200, 0.0
        hook = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                time.sleep(hook.delay)
                data = self.rfile.read(int(self.headers["Content-Length"]))
                code = hook.answer
                if code == 200:
                    hook.posts.append((dict(self.headers), json.loads(data)))
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bodies(self, route: str) -> list[dict]:
        return [body for _, body in self.posts if body["relay"]["route"] == route]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hooks():
    made = [Webhook(), Webhook()]
    yield made
    for hook in made:
        hook.close()


class Relay:
    def __init__(self, env: dict[str, str], state) -> None:
        self.port, self.state = free_port(), state
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("RELAY_")},
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

    def spooled(self, route: str) -> list[dict]:
        folder = self.state / "spool" / route
        return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))]

    def stop(self) -> str:
        self.process.terminate()
        said, _ = self.process.communicate(timeout=5)
        return said


def env_for(hooks) -> dict[str, str]:
    sous_chef, gatekeeper = hooks
    return {
        "RELAY_INBOUND_KEY": INBOUND,
        "GROK_WEBHOOK_URL": sous_chef.url,
        "GROK_WEBHOOK_KEY": SOUS_CHEF_KEY,
        "GATEKEEPER_WEBHOOK_URL": gatekeeper.url,
        "GATEKEEPER_WEBHOOK_KEY": GATEKEEPER_KEY,
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
    sous_chef, gatekeeper = hooks
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
    sous_chef, _ = hooks
    sent = {"kind": kind, "project": "jstack", "at": "x", "say": "jstack: 1 blocks", "items": []}

    relay.send(sent)

    until(lambda: sous_chef.bodies("blocking"))
    (paged,) = sous_chef.bodies("blocking")
    assert {k: v for k, v in paged.items() if k != "relay"} == sent


def test_a_body_with_nothing_that_blocks_goes_on_the_full_feed_only(relay, hooks):
    sous_chef, _ = hooks

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


def test_a_duplicate_id_is_sent_once_also_after_a_restart(hooks, tmp_path):
    sous_chef, _ = hooks
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
    sous_chef, _ = hooks

    relay.send({**body(event("merged", "quiet")), "id": "evt-1"})
    relay.send({**body(event("merged", "quiet", "beta")), "id": "evt-1"})

    until(lambda: sous_chef.bodies("everything"))
    time.sleep(0.3)
    (sent,) = sous_chef.bodies("everything")
    assert sent["relay"]["id"] == "evt-1" and sent["events"][0]["slug"] == "alpha"


def test_a_down_webhook_keeps_the_event_spooled_and_the_next_is_still_taken(relay, hooks):
    sous_chef, _ = hooks
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
    assert relay.spooled("blocking") == []
    log = relay.stop()
    assert f"relay: POST to sous-chef (blocking) failed for event {said['id']}: HTTP 503" in log
    assert SOUS_CHEF_KEY not in log


def test_a_slow_webhook_does_not_hold_back_taking_the_next_event(relay, hooks):
    sous_chef, _ = hooks
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
    sous_chef, _ = hooks
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
    sous_chef, _ = hooks
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
    sous_chef, _ = hooks
    sous_chef.answer = answer

    code, said = relay.send(body(event("gate", "user")))
    assert code == 202
    time.sleep(0.5)
    assert [b["relay"]["id"] for b in relay.spooled("blocking")] == [said["id"]]

    sous_chef.answer = 200
    until(lambda: sous_chef.bodies("blocking"))
    assert not (relay.state / "dead").exists()


def test_a_body_with_its_own_id_is_not_sent_again_after_the_window(hooks, tmp_path):
    sous_chef, _ = hooks
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
    sous_chef, _ = hooks
    sous_chef.answer = 409
    relay.send({**body(event("gate", "user")), "id": "conflict-1"})
    dead = relay.state / "dead" / "blocking"
    until(lambda: dead.is_dir() and list(dead.glob("*-conflict-1.json")))

    sous_chef.answer = 200
    code, later = relay.send(body(event("stall", "user", "beta")))

    until(lambda: sous_chef.bodies("blocking"))
    assert [b["relay"]["id"] for b in sous_chef.bodies("blocking")] == [later["id"]]
