"""The top-level webhook is the monitor of every project. When it differs from the project's own
webhook, jbus posts each event for the user, of every project, to both. With the same pair in both,
jbus posts it once. The two posts stay apart: each has its own outbox, five-minute gap, `last_error`
and streak. So a webhook that is down neither holds up nor repeats what jbus posts to the other.

Every test runs the real pass, or the real `wake.Box`, against the faked T3 Code server and webhooks
of `test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import Project, alert, wake
from test_jbus_kitchen import KEY, NOW, RESULT, Webhook
from view.scene import Scene, Served, iso

HELD = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"
DECIDED = (
    f'decision #9: {HELD}, a pull request jmerge holds for your word. Reply: "demo #9: merge it"'
)
GAINED = f"demo: {DECIDED}"
TOP_KEY = "top-level-key-0123456789"


@pytest.fixture
def top():
    fake = Webhook()
    yield fake
    fake.close()


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def monitored(kitchen, top):
    """Write the kitchen's config with a top-level pair beside the project's own."""
    kitchen.config(webhook_url=top.url + "/wake", webhook_key=KEY)


def held(kitchen):
    """Run a first pass, then have `jmerge` hold a pull request for the user, which is one
    `decision` event."""
    kitchen.poll()
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HELD + "\n")


def outbox(kitchen, route=""):
    return jbus.read_json(kitchen.state / route / "outbox.json", [])


def marks(kitchen, route=""):
    return jbus.read_json(kitchen.state / route / "wake.json", {})


def test_a_hold_is_posted_to_the_project_s_own_webhook_and_to_the_top_level_one(kitchen, top):
    monitored(kitchen, top)
    held(kitchen)
    said = kitchen.poll(later(10))
    assert kitchen.webhook.said == [[GAINED]]
    assert top.said == [[GAINED]]
    (own,), (other,) = kitchen.webhook.posts, top.posts
    assert own == other
    assert (other[0]["project"], other[0]["event"], other[0]["loud"]) == (
        "demo",
        "decision",
        "user",
    )
    assert outbox(kitchen) == [] and outbox(kitchen, "top-level") == []
    assert "woke demo: 1 events" in said


def test_a_quiet_event_goes_to_neither_webhook(kitchen, top):
    monitored(kitchen, top)
    kitchen.poll()
    box = wake.Box(kitchen.state, jbus.load().project("demo"), jbus.load().webhook)
    box.send("alpha", "result", "result alpha: done")
    box.send("alpha", "gate", "gate alpha: tea or coffee?")
    box.send("alpha", "decision", "decision alpha: which one?")
    kitchen.poll(later(10))
    assert kitchen.webhook.said == top.said == [["demo: decision alpha: which one?"]]


def test_a_failing_top_level_webhook_leaves_the_own_webhook_s_posts_and_outbox_alone(kitchen, top):
    monitored(kitchen, top)
    top.status = 500
    held(kitchen)
    kitchen.poll(later(10))
    assert kitchen.webhook.said == [[GAINED]] and outbox(kitchen) == []
    assert marks(kitchen)["last_error"] == ""
    assert [one["line"] for one in outbox(kitchen, "top-level")] == [DECIDED]
    assert marks(kitchen, "top-level")["last_error"] == "the webhook answered 500"
    for minutes in (16, 22, 28):
        kitchen.poll(later(minutes))
    key = alert.top_level(kitchen.state.name)
    assert key == "top-level webhook demo"
    streaks = kitchen.status()["streaks"]
    assert set(streaks) == {key} and streaks[key]["count"] == 4
    alerted = [line for post in kitchen.webhook.said for line in post if "alert" in line]
    assert alerted == [
        "demo: alert: top-level webhook demo failed 3 times in a row since "
        "11:10 ET: the webhook answered 500"
    ]
    assert kitchen.webhook.said[0] == [GAINED] and len(kitchen.webhook.said) == 2
    shown = kitchen.status()["projects"]["demo"]
    assert (shown["outbox"], shown["failed_wakes"], shown["last_error"]) == (0, 0, "")
    assert shown["top_level"] == {
        "outbox": 2,
        "failed_wakes": 4,
        "last_error": "the webhook answered 500",
    }
    top.status = 200
    kitchen.poll(later(34))
    assert top.said == [[GAINED, alerted[0]]]
    recovered = "recovered: top-level webhook demo after 4 failures since 11:10 ET"
    assert outbox(kitchen, "top-level") == outbox(kitchen) == []
    assert kitchen.lines("recovered") == [recovered]


def test_a_failing_own_webhook_leaves_the_top_level_webhook_s_posts_and_outbox_alone(kitchen, top):
    monitored(kitchen, top)
    kitchen.webhook.status = 500
    held(kitchen)
    kitchen.poll(later(10))
    assert top.said == [[GAINED]] and outbox(kitchen, "top-level") == []
    assert marks(kitchen, "top-level")["last_error"] == ""
    assert [one["line"] for one in outbox(kitchen)] == [DECIDED]
    assert marks(kitchen)["last_error"] == "the webhook answered 500"
    shown = kitchen.status()["projects"]["demo"]
    assert (shown["outbox"], shown["last_error"]) == (1, "the webhook answered 500")
    assert shown["top_level"] == {"outbox": 0, "failed_wakes": 0, "last_error": ""}
    kitchen.poll(later(12))
    assert top.said == [[GAINED]]


def test_the_same_pair_at_the_top_and_in_the_project_is_posted_once(kitchen):
    kitchen.config(webhook_url=kitchen.webhook.url + "/wake", webhook_key=KEY)
    held(kitchen)
    kitchen.poll(later(10))
    assert kitchen.webhook.said == [[GAINED]]
    assert not (kitchen.state / "top-level").exists()
    assert "top_level" not in kitchen.status()["projects"]["demo"]


def test_with_no_top_level_pair_there_is_one_webhook_as_before(kitchen):
    held(kitchen)
    kitchen.poll(later(10))
    assert kitchen.webhook.said == [[GAINED]]
    assert not (kitchen.state / "top-level").exists()


def test_a_project_with_no_pair_of_its_own_posts_to_the_top_level_pair_alone(tmp_path, top):
    inherits = Project(
        "demo", tmp_path / "checkout", "demo", "p-1", top.url, TOP_KEY, wake="webhook"
    )
    box = wake.Box(tmp_path / "state", inherits, (top.url, TOP_KEY))
    assert [route.top for route in box.routes] == [False]
    box.send("alpha", "decision", "decision alpha: which one?")
    assert box.flush(NOW, print) == 1
    assert top.said == [["demo: decision alpha: which one?"]]
    assert not (tmp_path / "state" / "top-level").exists()


def test_the_top_level_post_is_logged_apart_and_the_log_reads_one_event(kitchen, top):
    monitored(kitchen, top)
    held(kitchen)
    kitchen.poll(later(10))
    lines = (kitchen.state / wake.LOG).read_text().splitlines()
    records = [json.loads(line) for line in lines]
    (event,) = [one for one in records if one.get("event") == "decision"]
    assert [one["posted"] for one in records if "posted" in one] == [[event["id"]]]
    assert [one["posted_top_level"] for one in records if "posted_top_level" in one] == [
        [event["id"]]
    ]
    assert [one["line"] for one in kitchen.events("decision")] == [DECIDED]


def test_the_view_s_bus_shows_the_top_level_webhook_beside_the_own_one(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    status = json.loads((scene.state_dir / "status.json").read_text())
    failing = {"failed_wakes": 3, "last_error": "the webhook answered 500", "outbox": 1}
    status["projects"]["demo"]["top_level"] = failing
    scene.write("status.json", status, scene.state_dir)
    (scene.state / "top-level").mkdir()
    posted = NOW.timestamp() - 600
    scene.write("top-level/wake.json", {"posted": posted, "last_error": failing["last_error"]})
    served = Served(scene)
    try:
        bus = served.json("/state.json?project=demo")["bus"]
    finally:
        served.close()
    assert (bus["outbox"], bus["failed_wakes"], bus["last_error"]) == (2, 0, "")
    assert bus["top_level"] == {
        "outbox": 1,
        "failed_wakes": 3,
        "last_error": "the webhook answered 500",
        "posted": iso(datetime.fromtimestamp(posted, UTC)),
    }


def test_the_view_s_bus_has_no_top_level_part_where_the_project_has_one_webhook(
    tmp_path, monkeypatch
):
    served = Served(Scene(tmp_path, monkeypatch))
    try:
        assert served.json("/state.json?project=demo")["bus"]["top_level"] is None
    finally:
        served.close()


def test_a_top_level_pair_removed_and_given_back_posts_nothing_that_waited_before(kitchen, top):
    monitored(kitchen, top)
    top.status = 500
    held(kitchen)
    for minutes in (10, 16, 22):
        kitchen.poll(later(minutes))
    assert len(outbox(kitchen, "top-level")) == 2
    assert "top-level webhook demo" in kitchen.status()["streaks"]
    own = (outbox(kitchen), kitchen.webhook.said[:])
    kitchen.config()
    kitchen.poll(later(28))
    assert not (kitchen.state / "top-level").exists()
    assert "top-level webhook demo" not in kitchen.status()["streaks"]
    waited = [one["say"] for one in own[0]]
    assert waited and outbox(kitchen) == [] and kitchen.webhook.said == [*own[1], waited]
    assert marks(kitchen)["last_error"] == ""
    top.status = 200
    monitored(kitchen, top)
    kitchen.poll(later(34))
    assert top.said == []
    shown = kitchen.status()["projects"]["demo"]
    assert shown["top_level"] == {"outbox": 0, "failed_wakes": 0, "last_error": ""}
    assert (shown["outbox"], shown["last_error"]) == (0, "")
