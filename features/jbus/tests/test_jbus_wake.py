"""The second target is the one route that POSTs: it carries the key in two headers. Its tests
drive the real `wake.Box.flush_blocking` and `wake._post_blocking` against a target faked on a
local port. Like the real one, the fake answers 401 unless both headers carry the key exactly.
Nothing reaches the network.
"""

import http.server
import json
import threading
import urllib.request
from datetime import UTC, datetime

import pytest

from jbus import Project, wake

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
KEY = "wake-key-for-tests"


class Target:
    """The second target, faked on a local port."""

    def __init__(self, key=KEY):
        self.key, self.seen, self.posts, self.fail = key, [], [], set()
        self.refusal, self.refused, self.short = 500, b"", 0
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("content-length", 0)))
                fake.seen.append({name.lower(): value for name, value in self.headers.items()})
                took = (
                    self.headers.get("Authorization") == f"Bearer {fake.key}"
                    and self.headers.get("X-Automation-Key") == fake.key
                )
                status = 401 if not took else fake.refusal if len(fake.seen) in fake.fail else 200
                if status == 200:
                    fake.posts.append(json.loads(body))
                said = fake.refused if status not in (200, 401) else b""
                self.send_response(status)
                if fake.short:
                    self.send_header("transfer-encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(b"%x\r\n" % (len(said) + fake.short) + said)
                    return
                self.send_header("content-length", str(len(said)))
                self.end_headers()
                self.wfile.write(said)

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def target():
    fake = Target()
    yield fake
    fake.close()


def box(tmp_path, target=None, key=KEY):
    project = Project("demo", tmp_path / "checkout", "demo", "project-1")
    second = (f"{target.url}/relay", key) if target else ("", "")
    return wake.Box(tmp_path / "state", project, second)


ITEMS = {"kind": "blocking", "items": [{"key": "a"}]}


def second(made):
    """Post what waits for the second target, and return the count and what was said."""
    said = []
    return made.flush_blocking(NOW, said.append), said


def test_the_second_target_gets_the_key_in_both_headers_and_jbus_as_its_user_agent(
    tmp_path, target
):
    made = box(tmp_path, target)
    made.post(ITEMS)
    assert second(made) == (1, [])
    (seen,) = target.seen
    assert seen["authorization"] == f"Bearer {KEY}"
    assert seen["x-automation-key"] == KEY
    assert seen["content-type"] == "application/json"
    assert seen["user-agent"] == wake.AGENT and "jbus" in wake.AGENT
    assert target.posts == [ITEMS]
    assert made.waiting(made.blocking) == 0


@pytest.mark.parametrize(
    "kept",
    [
        {"Authorization": f"Bearer {KEY}"},
        {"X-Automation-Key": KEY},
        {"X-Jbus-Key": KEY},
    ],
    ids=["no-automation-key", "no-authorization", "the-old-header-alone"],
)
def test_a_post_without_both_headers_is_refused_and_the_outbox_is_kept(
    tmp_path, target, monkeypatch, kept
):
    request = urllib.request.Request

    def partial(url, *, data, headers, method):
        assert headers["Authorization"] == f"Bearer {KEY}" and headers[wake.HEADER] == KEY
        return request(
            url, data=data, headers={"content-type": headers["content-type"], **kept}, method=method
        )

    monkeypatch.setattr(wake.urllib.request, "Request", partial)
    made = box(tmp_path, target)
    made.post(ITEMS)
    assert second(made) == (0, ["wake failed demo blocking: the second target answered 401"])
    assert len(target.seen) == 1 and target.posts == []
    assert made.waiting(made.blocking) == 1
    assert made.marks(made.blocking)["last_error"] == "the second target answered 401"


@pytest.mark.parametrize("takes", [KEY, "another-key"], ids=["200", "401"])
def test_the_key_never_shows(tmp_path, capsys, takes):
    target = Target(takes)
    try:
        made = box(tmp_path, target)
        made.post(ITEMS)
        answer = wake._post_blocking(made.blocking, ITEMS)
        went = []
        took = made.flush_blocking(NOW, went.append, went=went.append)
    finally:
        target.close()
    refused = "the second target answered 401"
    assert (answer, took) == (("", 1) if takes == KEY else (refused, 0))
    assert target.seen[0]["x-automation-key"] == KEY
    assert went == ([""] if takes == KEY else [f"wake failed demo blocking: {refused}", refused])
    shown = [answer, *went, *capsys.readouterr()]
    shown += [(made.blocking.folder / name).read_text() for name in ("outbox.json", "wake.json")]
    assert all(KEY not in text for text in shown)


def test_a_403_is_a_failed_post_that_shows_no_url_and_no_key(tmp_path, target, capsys):
    target.fail, target.refusal = {1, 2}, 403
    made = box(tmp_path, target)
    made.post(ITEMS)
    assert wake._post_blocking(made.blocking, ITEMS) == "the second target answered 403"
    assert second(made) == (0, ["wake failed demo blocking: the second target answered 403"])
    shown = [made.marks(made.blocking)["last_error"], *capsys.readouterr()]
    shown += [(made.blocking.folder / name).read_text() for name in ("outbox.json", "wake.json")]
    assert all(KEY not in text and target.url not in text for text in shown)


DISABLED = b'{"success":false,"error":"Automation  wake-chef\\nis disabled"}'


def test_a_400_keeps_the_error_its_json_body_gives(tmp_path, target):
    target.fail, target.refusal, target.refused = {1, 2}, 400, DISABLED
    made = box(tmp_path, target)
    made.post(ITEMS)
    why = "the second target answered 400: Automation wake-chef is disabled"
    assert wake._post_blocking(made.blocking, ITEMS) == why
    assert second(made) == (0, [f"wake failed demo blocking: {why}"])
    assert made.marks(made.blocking)["last_error"] == why


@pytest.mark.parametrize(
    "body",
    [b"", b"<html>Bad Request</html>", b'{"success":false}', b'{"error":{"code":7}}', b"[1]"],
    ids=["empty", "html", "no-error", "not-text", "a-list"],
)
def test_a_refusal_with_no_error_text_says_only_the_code(tmp_path, target, body):
    target.fail, target.refusal, target.refused = {1}, 400, body
    made = box(tmp_path, target)
    assert wake._post_blocking(made.blocking, ITEMS) == "the second target answered 400"


def test_a_refusal_whose_body_is_cut_short_says_only_the_code(tmp_path, target):
    target.fail, target.refusal, target.refused, target.short = {1, 2}, 400, DISABLED, 10
    made = box(tmp_path, target)
    made.post(ITEMS)
    assert wake._post_blocking(made.blocking, ITEMS) == "the second target answered 400"
    assert second(made) == (0, ["wake failed demo blocking: the second target answered 400"])


def test_an_error_text_that_quotes_the_url_or_the_key_shows_neither(tmp_path, target):
    target.fail, target.refusal = {1}, 400
    url = f"{target.url}/relay"
    target.refused = json.dumps({"error": f"bad {url} with {KEY} " + "x" * 400}).encode()
    made = box(tmp_path, target)
    why = wake._post_blocking(made.blocking, ITEMS)
    assert why.startswith("the second target answered 400: bad [redacted] with [redacted] xxx")
    assert KEY not in why and url not in why and len(why) <= 300


def test_a_key_no_header_can_carry_is_a_failed_post_that_does_not_show_it(tmp_path, target, capsys):
    key = KEY + "\nX-Other: 1"
    made = box(tmp_path, target, key)
    made.post(ITEMS)
    unreached = "the second target could not be reached"
    assert wake._post_blocking(made.blocking, ITEMS) == unreached
    assert second(made) == (0, [f"wake failed demo blocking: {unreached}"])
    assert target.seen == []
    shown = [made.marks(made.blocking)["last_error"], *capsys.readouterr()]
    shown += [(made.blocking.folder / name).read_text() for name in ("outbox.json", "wake.json")]
    assert all(KEY not in text for text in shown)


def test_with_no_second_target_a_body_waits_nowhere_and_nothing_is_posted(tmp_path, monkeypatch):
    made = box(tmp_path)
    made.post(ITEMS)
    posted = []
    monkeypatch.setattr(wake, "_post_blocking", lambda *given: posted.append(given) or "")
    assert made.blocking is None and second(made) == (0, [])
    assert posted == [] and not (made.state / wake.BLOCKING).exists()
