"""A flush sends what waits for the home thread in bodies of bounded size, at most once in five
minutes. Each body is `{"kind": "events", "say": [...], "events": [...]}`: the lines for the chat,
and the events. The tests here hand `wake.Box.flush` a fake send, the way `jbus.alert` hands it a
send through T3 Code.

The second target is the one route that still POSTs: it carries the key in two headers. Its tests
drive the real `wake.Box.flush_blocking` and `wake._post_blocking` against a target faked on a
local port. Like the real one, the fake answers 401 unless both headers carry the key exactly.
Nothing reaches the network.
"""

import http.server
import json
import threading
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from jbus import Project, wake

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
KEY = "wake-key-for-tests"
REFUSED = "T3 Code did not take the wake: no"


class Thread:
    """A home thread faked as the send that `flush` calls: it keeps each body it took, and refuses
    the sends whose number is in `fail`."""

    def __init__(self):
        self.posts, self.sizes, self.tries, self.fail = [], [], 0, set()

    def __call__(self, made):
        self.tries += 1
        if self.tries in self.fail:
            return REFUSED
        self.posts.append(made)
        self.sizes.append(len(json.dumps(made).encode()))
        return ""


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
def thread():
    return Thread()


@pytest.fixture
def target():
    fake = Target()
    yield fake
    fake.close()


def box(tmp_path, target=None, key=KEY):
    project = Project("demo", tmp_path / "checkout", "demo", "project-1")
    second = (f"{target.url}/relay", key) if target else ("", "")
    return wake.Box(tmp_path / "state", project, second)


def waiting(made):
    return json.loads((made.home.folder / "outbox.json").read_text())


def flush(made, thread, now=NOW):
    said = []
    return made.flush(now, said.append, post=thread), said


def sent(thread):
    return [event for post in thread.posts for event in post["events"]]


def test_a_flush_sends_one_body_with_the_chat_lines_and_the_events(tmp_path, thread):
    made = box(tmp_path)
    made.send("alpha", "decision", "decision alpha: which?")
    assert flush(made, thread) == (1, [])
    (post,) = thread.posts
    assert sorted(post) == ["events", "kind", "say"] and post["say"] == [
        "demo: decision alpha: which?"
    ]
    assert post["kind"] == "events"
    assert [event["line"] for event in post["events"]] == ["decision alpha: which?"]
    assert waiting(made) == []


def test_a_body_carries_the_lines_for_the_chat_at_its_top_in_order(tmp_path, thread):
    made = box(tmp_path)
    made.send("", "heartbeat", "heartbeat: jbus alive")
    made.send("alpha", "alert", "alert alpha: no pass in an hour")
    made.send("alpha", "result", "result alpha: done")
    made.send("beta", "decision", "decision beta: which?")
    assert flush(made, thread) == (2, [])
    (post,) = thread.posts
    assert post["say"] == ["demo: alert alpha: no pass in an hour", "demo: decision beta: which?"]
    assert [event.get("say") for event in post["events"]] == post["say"]


def test_quiet_events_start_no_wake_and_go_with_none_that_is_started(tmp_path, thread):
    made = box(tmp_path)
    made.send("", "heartbeat", "heartbeat: jbus alive")
    made.send("#7", "jmerge", "wait 7 its check has not passed")
    made.send("alpha", "result", "result alpha: done")
    heard = []
    assert made.flush(NOW, heard.append, post=thread, went=heard.append) == 0
    assert heard == [] and thread.tries == 0 and "posted" not in made.marks(made.home)
    assert made.waiting() == 0
    made.send("alpha", "decision", "decision alpha: which?")
    assert made.flush(NOW, heard.append, post=thread, went=heard.append) == 1
    assert heard == [""] and [event["event"] for event in sent(thread)] == ["decision"]
    assert [one["event"] for one in made.log() if one["posted"] is None] == [
        "heartbeat",
        "jmerge",
        "result",
    ]


def test_a_refused_send_keeps_the_outbox_and_says_why(tmp_path, thread):
    thread.fail = {1}
    made = box(tmp_path)
    made.send("alpha", "decision", "one")
    made.send("beta", "decision", "two")
    before = waiting(made)
    assert flush(made, thread) == (0, [f"wake failed demo home thread: {REFUSED}"])
    assert thread.posts == [] and waiting(made) == before
    assert made.marks(made.home)["last_error"] == REFUSED
    assert made.marks()["failed"] == 1


def backlog(made: wake.Box) -> list[dict]:
    events: list[dict] = []
    while len(json.dumps(events).encode()) <= 2 * wake.WAKE_CAP:
        slug = f"task-{len(events) + 1}"
        made.send(slug, "decision", f"gate {slug}", "x" * 7000)
        events = waiting(made)
    assert len(json.dumps(events[:-1]).encode()) <= 2 * wake.WAKE_CAP
    return events


def test_a_backlog_goes_as_bounded_bodies_in_order_in_one_flush(tmp_path, thread):
    made = box(tmp_path)
    events = backlog(made)
    assert flush(made, thread) == (len(events), [])
    assert len(thread.posts) == 3
    assert sent(thread) == events
    assert all(size <= wake.WAKE_CAP for size in thread.sizes)
    assert waiting(made) == []
    assert made.marks(made.home)["posted"] == NOW.timestamp()


def test_a_list_that_fails_and_what_follows_it_wait_in_order_for_the_next_flush(tmp_path, thread):
    made = box(tmp_path)
    events = backlog(made)
    thread.fail = {2}
    went = []
    took = made.flush(NOW, lambda _: None, post=thread, went=went.append)
    (first,) = thread.posts
    assert took == len(first["events"]) and went == ["", REFUSED]
    assert thread.tries == 2
    assert waiting(made) == events[took:]
    assert (made.marks()["failed"], made.marks(made.home)["last_error"]) == (1, REFUSED)
    assert flush(made, thread, NOW + timedelta(seconds=wake.GAP - 1)) == (0, [])
    assert flush(made, thread, NOW + timedelta(seconds=wake.GAP)) == (len(events) - took, [])
    assert len(thread.posts) == 3
    assert sent(thread) == events
    assert waiting(made) == [] and made.marks(made.home)["last_error"] == ""


def test_a_flush_stopped_in_its_first_send_still_waits_the_gap(tmp_path, thread):
    class Stopped(BaseException):
        pass

    def stopped(made):
        raise Stopped

    made = box(tmp_path)
    made.send("alpha", "decision", "decision alpha: a line")
    with pytest.raises(Stopped):
        made.flush(NOW, post=stopped)
    assert made.marks(made.home)["posted"] == NOW.timestamp()
    assert flush(made, thread, NOW + timedelta(seconds=wake.GAP - 1)) == (0, [])
    assert thread.posts == []
    assert flush(made, thread, NOW + timedelta(seconds=wake.GAP)) == (1, [])


def test_an_event_larger_than_one_body_may_carry_goes_alone(tmp_path, thread):
    made = box(tmp_path)
    small = wake.event("demo", "small", "decision", "small")
    text = "x" * wake.WAKE_CAP
    large = wake.event("demo", "large", "decision", "large", text, cap=2 * len(text))
    made.home.folder.mkdir(parents=True)
    (made.home.folder / "outbox.json").write_text(json.dumps([small, large, small]))
    assert flush(made, thread) == (3, [])
    assert [post["events"] for post in thread.posts] == [[small], [large], [small]]


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
