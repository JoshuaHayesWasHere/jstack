"""A wake carries the key in the two headers that the Chef's webhook takes, in POSTs of bounded
size. Each POST is `{"say": [...], "events": [...]}`: the lines for the chat, and the events.

Every test drives the real `wake.Box` and `wake._post` against a webhook faked on a local port. Like
the real one, the fake answers 401 unless both headers carry the key exactly. Nothing reaches the
network.
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


class Webhook:
    def __init__(self, key=KEY):
        self.key, self.seen, self.posts, self.sizes, self.fail = key, [], [], [], set()
        self.refusal, self.refused = 500, b""
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
                    fake.sizes.append(len(body))
                said = fake.refused if status not in (200, 401) else b""
                self.send_response(status)
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
def webhook():
    fake = Webhook()
    yield fake
    fake.close()


def box(tmp_path, webhook, key=KEY):
    project = Project("demo", tmp_path / "checkout", "demo", "project-1", webhook.url, key)
    return wake.Box(tmp_path / "state", project)


def waiting(made):
    return json.loads((made.state / "outbox.json").read_text())


def flush(made, now=NOW):
    said = []
    return made.flush(now, said.append), said


def sent(webhook):
    return [event for post in webhook.posts for event in post["events"]]


def test_a_flush_carries_the_key_in_both_headers_and_is_taken(tmp_path, webhook):
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "decision alpha: which?")
    assert flush(made) == (1, [])
    (seen,) = webhook.seen
    assert seen["authorization"] == f"Bearer {KEY}"
    assert seen["x-automation-key"] == KEY
    assert seen["content-type"] == "application/json"
    assert "x-jbus-key" not in seen
    (post,) = webhook.posts
    assert sorted(post) == ["events", "kind", "say"] and post["say"] == [
        "demo: decision alpha: which?"
    ]
    assert post["kind"] == "events"
    assert [event["line"] for event in post["events"]] == ["decision alpha: which?"]
    assert waiting(made) == []


def test_a_post_names_jbus_as_its_user_agent_and_not_urllib(tmp_path, webhook):
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "decision alpha: which?")
    assert wake._post(made.routes[0], waiting(made)) == ""
    (seen,) = webhook.seen
    assert seen["user-agent"] == wake.AGENT and "jbus" in wake.AGENT
    assert not seen["user-agent"].startswith("Python-urllib")


def test_a_post_carries_the_lines_for_the_chat_at_its_top_in_order(tmp_path, webhook):
    made = box(tmp_path, webhook)
    made.send("", "heartbeat", "heartbeat: jbus alive")
    made.send("alpha", "alert", "alert alpha: no pass in an hour")
    made.send("alpha", "result", "result alpha: done")
    made.send("beta", "decision", "decision beta: which?")
    assert flush(made) == (2, [])
    (post,) = webhook.posts
    assert post["say"] == ["demo: alert alpha: no pass in an hour", "demo: decision beta: which?"]
    assert [event.get("say") for event in post["events"]] == post["say"]


def test_quiet_events_start_no_post_and_go_with_none_that_is_started(tmp_path, webhook):
    made = box(tmp_path, webhook)
    made.send("", "heartbeat", "heartbeat: jbus alive")
    made.send("#7", "jmerge", "wait 7 its check has not passed")
    made.send("alpha", "result", "result alpha: done")
    heard = []
    assert made.flush(NOW, heard.append, went=heard.append) == 0
    assert heard == [] and webhook.seen == [] and "posted" not in made.marks()
    assert made.waiting() == 0
    made.send("alpha", "decision", "decision alpha: which?")
    assert made.flush(NOW, heard.append, went=heard.append) == 1
    assert heard == [""] and [event["event"] for event in sent(webhook)] == ["decision"]
    assert [one["event"] for one in made.log() if one["posted"] is None] == [
        "heartbeat",
        "jmerge",
        "result",
    ]


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
    tmp_path, webhook, monkeypatch, kept
):
    request = urllib.request.Request

    def partial(url, *, data, headers, method):
        assert headers["Authorization"] == f"Bearer {KEY}" and headers[wake.HEADER] == KEY
        return request(
            url, data=data, headers={"content-type": headers["content-type"], **kept}, method=method
        )

    monkeypatch.setattr(wake.urllib.request, "Request", partial)
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "one")
    made.send("beta", "decision", "two")
    before = waiting(made)
    assert flush(made) == (0, ["wake failed demo: the webhook answered 401"])
    assert len(webhook.seen) == 1 and webhook.posts == []
    assert waiting(made) == before
    assert made.marks()["last_error"] == "the webhook answered 401"


@pytest.mark.parametrize("takes", [KEY, "another-key"], ids=["200", "401"])
def test_the_key_never_shows(tmp_path, capsys, takes):
    webhook = Webhook(takes)
    try:
        made = box(tmp_path, webhook)
        made.send("alpha", "decision", "decision alpha: which?", "the text", key="gate|alpha|which")
        answer = wake._post(made.routes[0], waiting(made))
        went = []
        took = made.flush(NOW, went.append, went=went.append)
    finally:
        webhook.close()
    assert (answer, took) == (("", 1) if takes == KEY else ("the webhook answered 401", 0))
    assert webhook.seen[0]["x-automation-key"] == KEY
    failed = ["wake failed demo: the webhook answered 401", "the webhook answered 401"]
    assert went == ([""] if takes == KEY else failed)
    shown = [answer, *went, *capsys.readouterr()]
    shown += [(made.state / name).read_text() for name in ("outbox.json", "wake.json", "sent.json")]
    assert all(KEY not in text for text in shown)


def test_a_403_is_a_failed_post_that_shows_no_url_and_no_key(tmp_path, webhook, capsys):
    webhook.fail, webhook.refusal = {1, 2}, 403
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "one")
    assert wake._post(made.routes[0], waiting(made)) == "the webhook answered 403"
    assert flush(made) == (0, ["wake failed demo: the webhook answered 403"])
    shown = [made.marks()["last_error"], *capsys.readouterr()]
    shown += [(made.state / name).read_text() for name in ("outbox.json", "wake.json")]
    assert all(KEY not in text and webhook.url not in text for text in shown)


DISABLED = b'{"success":false,"error":"Automation  wake-chef\\nis disabled"}'


def test_a_400_keeps_the_error_its_json_body_gives(tmp_path, webhook):
    webhook.fail, webhook.refusal, webhook.refused = {1, 2}, 400, DISABLED
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "one")
    why = "the webhook answered 400: Automation wake-chef is disabled"
    assert wake._post(made.routes[0], waiting(made)) == why
    assert flush(made) == (0, [f"wake failed demo: {why}"])
    assert made.marks()["last_error"] == why


@pytest.mark.parametrize(
    "body",
    [b"", b"<html>Bad Request</html>", b'{"success":false}', b'{"error":{"code":7}}', b"[1]"],
    ids=["empty", "html", "no-error", "not-text", "a-list"],
)
def test_a_refusal_with_no_error_text_says_only_the_code(tmp_path, webhook, body):
    webhook.fail, webhook.refusal, webhook.refused = {1}, 400, body
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "one")
    assert wake._post(made.routes[0], waiting(made)) == "the webhook answered 400"


def test_an_error_text_that_quotes_the_url_or_the_key_shows_neither(tmp_path, webhook):
    webhook.fail, webhook.refusal = {1}, 400
    webhook.refused = json.dumps({"error": f"bad {webhook.url}/wake with {KEY} " + "x" * 400})
    webhook.refused = webhook.refused.encode()
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "one")
    why = wake._post(made.routes[0], waiting(made))
    assert why.startswith("the webhook answered 400: bad [webhook]/wake with [webhook] xxx")
    assert KEY not in why and webhook.url not in why and len(why) <= 300


def test_a_key_no_header_can_carry_is_a_failed_post_that_does_not_show_it(
    tmp_path, webhook, capsys
):
    key = KEY + "\nX-Other: 1"
    made = box(tmp_path, webhook, key)
    made.send("alpha", "decision", "one")
    assert wake._post(made.routes[0], waiting(made)) == "the webhook could not be reached"
    assert flush(made) == (0, ["wake failed demo: the webhook could not be reached"])
    assert webhook.seen == []
    shown = [made.marks()["last_error"], *capsys.readouterr()]
    shown += [(made.state / name).read_text() for name in ("outbox.json", "wake.json")]
    assert all(KEY not in text for text in shown)


def backlog(made: wake.Box) -> list[dict]:
    events: list[dict] = []
    while len(json.dumps(events).encode()) <= 2 * wake.WAKE_CAP:
        slug = f"task-{len(events) + 1}"
        made.send(slug, "decision", f"gate {slug}", "x" * 7000)
        events = waiting(made)
    assert len(json.dumps(events[:-1]).encode()) <= 2 * wake.WAKE_CAP
    return events


def test_a_backlog_goes_as_bounded_posts_in_order_in_one_flush(tmp_path, webhook):
    made = box(tmp_path, webhook)
    events = backlog(made)
    assert flush(made) == (len(events), [])
    assert len(webhook.posts) == 3
    assert sent(webhook) == events
    assert all(size <= wake.WAKE_CAP for size in webhook.sizes)
    assert waiting(made) == []
    assert made.marks()["posted"] == NOW.timestamp()


def test_a_list_that_fails_and_what_follows_it_wait_in_order_for_the_next_flush(tmp_path, webhook):
    made = box(tmp_path, webhook)
    events = backlog(made)
    webhook.fail = {2}
    went = []
    took = made.flush(NOW, lambda _: None, went=went.append)
    (first,) = webhook.posts
    assert took == len(first["events"]) and went == ["", "the webhook answered 500"]
    assert len(webhook.seen) == 2
    assert waiting(made) == events[took:]
    assert (made.marks()["failed"], made.marks()["last_error"]) == (1, "the webhook answered 500")
    assert flush(made, NOW + timedelta(seconds=wake.GAP - 1)) == (0, [])
    assert flush(made, NOW + timedelta(seconds=wake.GAP)) == (len(events) - took, [])
    assert len(webhook.posts) == 3
    assert sent(webhook) == events
    assert waiting(made) == [] and made.marks()["last_error"] == ""


def test_a_flush_stopped_in_its_first_post_still_waits_the_gap(tmp_path, webhook, monkeypatch):
    class Stopped(BaseException):
        pass

    def stopped(route, events):
        raise Stopped

    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "decision alpha: a line")
    with monkeypatch.context() as patch:
        patch.setattr(wake, "_post", stopped)
        with pytest.raises(Stopped):
            made.flush(NOW)
    assert made.marks()["posted"] == NOW.timestamp()
    assert flush(made, NOW + timedelta(seconds=wake.GAP - 1)) == (0, [])
    assert webhook.posts == []
    assert flush(made, NOW + timedelta(seconds=wake.GAP)) == (1, [])


def test_an_event_larger_than_one_post_may_carry_goes_alone(tmp_path, webhook):
    made = box(tmp_path, webhook)
    small = wake.event("demo", "small", "decision", "small")
    text = "x" * wake.WAKE_CAP
    large = wake.event("demo", "large", "decision", "large", text, cap=2 * len(text))
    made.state.mkdir(parents=True)
    (made.state / "outbox.json").write_text(json.dumps([small, large, small]))
    assert flush(made) == (3, [])
    assert [post["events"] for post in webhook.posts] == [[small], [large], [small]]
