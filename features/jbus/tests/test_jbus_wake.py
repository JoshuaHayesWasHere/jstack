"""The second target is the one route that POSTs: it carries the key in two headers. Its tests
drive the real `wake.Box.flush_blocking` and `wake._post_blocking` against a target faked on a
local port. Like the real one, the fake answers 401 unless both headers carry the key exactly.
Nothing reaches the network.
"""

import http.server
import json
import subprocess
import sys
import threading
import urllib.request
from datetime import UTC, datetime

import pytest

from jbus import Project, relay, wake

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
    (posted,) = target.posts
    assert {key: value for key, value in posted.items() if key != "id"} == ITEMS
    assert relay.event_id(posted) == posted["id"]
    assert made.waiting(made.blocking) == 0


def test_the_same_body_queued_again_later_gets_an_id_of_its_own(tmp_path, target):
    """The relay sends a body on once ever under its own id, so a retry keeps the id it was queued
    with and the same alert queued again is a new body, which the relay sends too."""
    made = box(tmp_path, target)
    made.post(ITEMS)
    made.post(ITEMS)
    (first, again) = wake.read_json(made.blocking.folder / "outbox.json", [])
    assert first["id"] != again["id"]
    assert relay.event_id(first) == first["id"] and relay.event_id(again) == again["id"]


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


def test_an_error_text_that_quotes_the_url_or_the_key_shows_neither(tmp_path, target):
    target.fail, target.refusal = {1}, 400
    url = f"{target.url}/relay"
    target.refused = json.dumps({"error": f"bad {url} with {KEY} " + "x" * 400}).encode()
    made = box(tmp_path, target)
    why = wake._post_blocking(made.blocking, ITEMS)
    assert why.startswith("the second target answered 400: bad [redacted] with [redacted] xxx")
    assert KEY not in why and url not in why and len(why) <= 300


def test_with_no_second_target_a_body_waits_nowhere_and_nothing_is_posted(tmp_path, monkeypatch):
    made = box(tmp_path)
    made.post(ITEMS)
    posted = []
    monkeypatch.setattr(wake, "_post_blocking", lambda *given: posted.append(given) or "")
    assert made.blocking is None and second(made) == (0, [])
    assert posted == [] and not (made.state / wake.BLOCKING).exists()


def test_a_key_sent_once_is_never_sent_again_by_this_process_or_another(tmp_path):
    """A pass and a `jbus tick` are two processes that send under the same keys. Each must see
    the keys the other sent, however many it has already looked up, and `sent.json` stays the
    list of keys in the order they were sent."""
    made = box(tmp_path)
    assert made.send("s", "merged", "first", key="one") is True
    assert made.send("s", "merged", "again", key="one") is False
    other = (
        "import sys; from pathlib import Path; from jbus import Project, wake\n"
        "project = Project('demo', Path(sys.argv[1]) / 'checkout', 'demo', 'project-1')\n"
        "made = wake.Box(Path(sys.argv[1]) / 'state', project)\n"
        "print(made.send('s', 'merged', 'tick one', key='one'),"
        " made.send('s', 'merged', 'tick two', key='two'))\n"
    )
    ran = subprocess.run(
        [sys.executable, "-c", other, str(tmp_path)], capture_output=True, text=True, check=True
    )
    assert ran.stdout.split() == ["False", "True"]
    assert made.send("s", "merged", "pass two", key="two") is False
    assert made.send("s", "merged", "pass three", key="three") is True
    assert json.loads((tmp_path / "state" / "sent.json").read_text()) == ["one", "two", "three"]
    assert made.sent() == ["one", "two", "three"]
    assert [one["line"] for one in made.log()] == ["first", "tick two", "pass three"]


def test_an_unmarked_key_is_sent_again_and_the_other_keys_keep_their_order(tmp_path):
    """A launch marked before it ran that T3 Code then refused forgets its key, so the next
    pass launches it; a key never marked is no error."""
    made = box(tmp_path)
    for key in ("one", "two", "three"):
        made.mark(key)
    made.unmark("two")
    made.unmark("never")
    assert made.sent() == ["one", "three"]
    assert made.send("s", "merged", "again", key="two") is True
    assert made.sent() == ["one", "three", "two"]


def test_a_keyed_send_parses_sent_json_again_only_once_another_process_wrote_it(
    tmp_path, monkeypatch
):
    """`sent.json` holds every key a project ever sent, 4 MB on a busy one, and a pass sends
    under hundreds of keys. Parsing it whole for each of them was 1.35 s of a pass."""
    made = box(tmp_path)
    sent = tmp_path / "state" / "sent.json"
    parsed = []
    real = wake.read_json
    monkeypatch.setattr(
        wake, "read_json", lambda path, *rest: (parsed.append(path), real(path, *rest))[1]
    )
    made.send("s", "merged", "first", key="first")
    for n in range(20):
        made.send("s", "merged", f"line {n}", key=f"key {n}")
        made.send("s", "merged", f"line {n} again", key=f"key {n}")
    assert parsed.count(sent) == 0
    sent.write_text(json.dumps([*json.loads(sent.read_text()), "from a tick"]))
    assert made.send("s", "merged", "the tick's", key="from a tick") is False
    assert made.send("s", "merged", "then", key="then") is True
    assert parsed.count(sent) == 1


class Died(BaseException):
    """The pass dies here, between two of its writes."""


def test_a_keyed_line_a_pass_appended_and_died_after_is_logged_once(tmp_path, monkeypatch):
    """A keyed line waits with its key in `unlogged.json` until both are written: a pass that died
    after it appended the line, before it cleared `unlogged.json`, leaves the line to stand once."""
    made, real = box(tmp_path), wake.store.append_jsonl

    def dying(path, lines, **kwargs):
        real(path, lines, **kwargs)
        if lines:
            raise Died

    monkeypatch.setattr(wake.store, "append_jsonl", dying)
    with pytest.raises(Died):
        made.send("alpha", "stall", "stall alpha", key="stall|alpha")
    monkeypatch.setattr(wake.store, "append_jsonl", real)
    assert made.send("alpha", "stall", "stall alpha", key="stall|alpha") is False
    assert [one["line"] for one in made.log()] == ["stall alpha"]


def test_two_equal_lines_under_two_keys_in_one_second_are_both_logged(tmp_path, monkeypatch):
    """Equal lines are two events (`wake.entries`): a keyed line is not taken for one a dead pass
    appended because the log ends with its words."""
    made = box(tmp_path)
    monkeypatch.setattr(wake.Box, "clock", staticmethod(lambda: datetime(2026, 11, 11, tzinfo=UTC)))
    assert made.send("alpha", "condition", "T3 Code could not be asked", key="t3 day-1")
    assert made.send("alpha", "condition", "T3 Code could not be asked", key="t3 day-2")
    assert [one["line"] for one in made.log()] == ["T3 Code could not be asked"] * 2


def test_the_prune_writes_a_keyed_line_a_dead_pass_left_waiting_first(tmp_path, monkeypatch):
    made, real = box(tmp_path), wake.store.append_jsonl

    def died(path, lines, **kwargs):
        if lines:
            raise Died

    monkeypatch.setattr(wake.store, "append_jsonl", died)
    with pytest.raises(Died):
        made.send("alpha", "stall", "stall alpha", key="stall|alpha")
    monkeypatch.setattr(wake.store, "append_jsonl", real)
    made.forget(datetime(2000, 1, 1, tzinfo=UTC), 0)
    assert [one["line"] for one in made.log()] == ["stall alpha"]
    assert made.has("stall|alpha")


def test_a_line_jbus_could_not_write_goes_into_the_log_before_the_next(tmp_path, monkeypatch):
    made, real = box(tmp_path), wake.store.append_jsonl

    def full(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(wake.store, "append_jsonl", full)
    made.send("alpha", "stall", "first")
    monkeypatch.setattr(wake.store, "append_jsonl", real)
    made.send("alpha", "stall", "second")
    assert [one["line"] for one in made.log()] == ["first", "second"]
