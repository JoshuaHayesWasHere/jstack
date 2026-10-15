"""What blocks, and the second target that is posted it.

An item blocks when it is open and nothing can move without the user (`waiting.blocking`).
The second target, the config's top-level `blocking_url` and `blocking_key`, is posted the
items that open in a pass (`kind: "events"`), one reminder for each item still open
`REMIND_MINUTES` after it opened (`kind: "reminder"`), and on the pass that begins each
`REFRESH_MINUTES` every open item, oldest first, also none (`kind: "refresh"`). It is its own
route: its own outbox, gap, streak and status. Every other body says `kind: "events"`.

Every test runs the real pass against the faked T3 Code server and webhooks of
`test_jbus_kitchen`. Nothing reaches the network.
"""

from datetime import timedelta

import pytest

import jbus
from jbus import alert, leftover, waiting, wake
from test_jbus_kitchen import KEY, NOW, RESULT, Webhook
from test_jbus_questions import gate

SECOND_KEY = "blocking-key-0123456789"
NINE = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"
TEN = "hold 10 https://example.test/pull/10: needs user, touches skills/home/SKILL.md"


@pytest.fixture
def second():
    fake = Webhook()
    yield fake
    fake.close()


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def relayed(kitchen, second):
    """The kitchen's config with the second target set, and a first pass."""
    kitchen.config(blocking_url=second.url + "/relay", blocking_key=SECOND_KEY)
    kitchen.poll()


def hold(kitchen, *numbers):
    """The pull requests `jmerge` holds for the user, by number: 9, 10 or both."""
    lines = {9: NINE, 10: TEN}
    for number in numbers:
        kitchen.brief(f"held{number}", RESULT)
    kitchen.set("open.json", [kitchen.opened(f"held{number}", number) for number in numbers])
    kitchen.set("jmerge.txt", "".join(lines[number] + "\n" for number in numbers))


def kinds(fake):
    return [body["kind"] for body in fake.bodies]


def keys(body):
    return [one["key"] for one in body["items"]]


def test_the_timers_sit_beside_close_minutes():
    assert (leftover.CLOSE_MINUTES, leftover.REMIND_MINUTES, leftover.REFRESH_MINUTES) == (
        30,
        15,
        60,
    )


def test_an_item_that_stays_15_minutes_is_reminded_of_once(kitchen, second):
    relayed(kitchen, second)
    hold(kitchen, 9)
    kitchen.poll(later(1))
    (opened,) = second.bodies
    assert opened["kind"] == "events" and keys(opened) == ["#9"]
    assert opened["items"][0]["case"] == "c" and opened["events"] == []
    kitchen.poll(later(10))
    assert kinds(second) == ["events"]
    kitchen.poll(later(16))
    assert kinds(second) == ["events", "reminder"]
    reminder = second.bodies[-1]
    assert keys(reminder) == ["#9"] and reminder["project"] == "demo"
    assert reminder["say"] == [f"demo: reminder {NINE}"]
    for minutes in (17, 31, 45):
        kitchen.poll(later(minutes))
    assert kinds(second) == ["events", "reminder"]
    assert jbus.read_json(kitchen.state / waiting.BLOCKS, {})["reminded"].keys() == {"#9"}


def test_an_item_closed_at_10_minutes_gets_no_reminder(kitchen, second):
    relayed(kitchen, second)
    hold(kitchen, 9)
    kitchen.poll(later(1))
    hold(kitchen)
    kitchen.poll(later(10))
    for minutes in (16, 20, 40):
        kitchen.poll(later(minutes))
    assert kinds(second) == ["events"]


def test_the_refresh_lists_every_open_item_oldest_first(kitchen, second):
    relayed(kitchen, second)
    hold(kitchen, 10)
    kitchen.poll(later(5))
    hold(kitchen, 9, 10)
    kitchen.poll(later(20))
    kitchen.poll(later(59))
    assert "refresh" not in kinds(second)
    kitchen.poll(later(60))
    (refresh,) = [body for body in second.bodies if body["kind"] == "refresh"]
    assert keys(refresh) == ["#10", "#9"]
    kitchen.poll(later(61))
    assert kinds(second).count("refresh") == 1


def test_with_nothing_open_the_refresh_is_an_empty_list(kitchen, second):
    relayed(kitchen, second)
    kitchen.poll(later(30))
    assert second.bodies == []
    kitchen.poll(later(61))
    (refresh,) = second.bodies
    assert (refresh["kind"], refresh["items"], refresh["say"]) == (
        "refresh",
        [],
        ["demo: nothing blocks"],
    )
    kitchen.poll(later(121))
    assert kinds(second) == ["refresh", "refresh"]


def test_every_body_has_its_kind(kitchen, second):
    relayed(kitchen, second)
    hold(kitchen, 9)
    for minutes in (1, 16, 60):
        kitchen.poll(later(minutes))
    assert kinds(second) == ["events", "reminder", "refresh"]
    assert {body["kind"] for body in kitchen.webhook.bodies} == {"events"}
    assert all(sorted(body) == ["events", "kind", "say"] for body in kitchen.webhook.bodies)


def test_the_second_target_gets_what_blocks_and_nothing_quiet(kitchen, second):
    relayed(kitchen, second)
    kitchen.brief("alpha", "Thread: mcp:crew-alpha\n")
    kitchen.brief("beta", "Thread: mcp:crew-beta\n")
    assert kitchen.main("gate", "alpha", stdin=gate("tea or coffee?", "alpha"))[0] == 0
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo"), config.webhook).send(
        "alpha", "result", "result alpha: done"
    )
    asked = gate("may I deploy the site tonight?", "beta")
    assert kitchen.main("gate", "beta", stdin=asked)[0] == 0
    kitchen.poll(later(1))
    said = [line for post in kitchen.webhook.said for line in post]
    assert any("tea or coffee?" in line for line in said)
    (opened,) = second.bodies
    assert keys(opened) == ["gate:q2"]
    assert opened["items"][0]["why"] == "always-pause: deploy"
    assert not any("result alpha" in line for body in second.bodies for line in body["say"])


def test_a_defaulted_gate_whose_slug_goes_silent_becomes_a_stall(kitchen, second):
    kitchen.monkeypatch.setattr(wake.Box, "clock", staticmethod(lambda: NOW))
    relayed(kitchen, second)
    kitchen.brief("alpha", "Thread: mcp:crew-alpha\n")
    kitchen.main("gate", "alpha", stdin=gate("tea or coffee?", "alpha"))
    kitchen.poll(later(10))
    assert second.bodies == []
    kitchen.poll(later(31))
    (opened,) = second.bodies
    assert keys(opened) == ["gate:q1"] and opened["items"][0]["case"] == "d"
    kitchen.poll(later(40))
    assert kinds(second) == ["events"]


def test_a_failing_second_target_leaves_the_others_alone(kitchen, second):
    relayed(kitchen, second)
    second.status = 500
    hold(kitchen, 9)
    for minutes in (1, 7, 13):
        kitchen.poll(later(minutes))
    gained = "waiting demo: 1 wait on user, 1 new (hold 9), 0 gone"
    assert kitchen.webhook.said[0] == [gained]
    assert jbus.read_json(kitchen.state / "outbox.json", []) == []
    shown = kitchen.status()["projects"]["demo"]
    assert (shown["outbox"], shown["last_error"]) == (0, "")
    assert shown["blocking"] == {
        "outbox": 1,
        "failed_wakes": 3,
        "last_error": "the webhook answered 500",
    }
    assert set(kitchen.status()["streaks"]) == {alert.blocking("demo")}
    alerted = [line for post in kitchen.webhook.said for line in post if "alert" in line]
    assert alerted == [
        "demo: alert: blocking webhook demo failed 3 times in a row since "
        "11:01 ET: the webhook answered 500"
    ]
    second.status = 200
    kitchen.poll(later(16))
    assert kinds(second) == ["events", "reminder"]


def test_a_reminder_does_not_wait_on_the_gap(kitchen, second):
    relayed(kitchen, second)
    hold(kitchen, 10)
    kitchen.poll(later(1))
    hold(kitchen, 9, 10)
    kitchen.poll(later(14))
    kitchen.poll(later(16))
    assert kinds(second) == ["events", "events", "reminder"]


def test_with_no_second_pair_nothing_is_posted_beyond_the_events(kitchen):
    kitchen.poll()
    hold(kitchen, 9)
    for minutes in (1, 16, 61):
        kitchen.poll(later(minutes))
    assert {body["kind"] for body in kitchen.webhook.bodies} == {"events"}
    assert not (kitchen.state / "blocking").exists()
    assert "blocking" not in kitchen.status()["projects"]["demo"]


@pytest.mark.parametrize("given", [{"blocking_url": "https://relay.test"}, {"blocking_key": KEY}])
def test_half_the_second_pair_is_refused(kitchen, given):
    kitchen.config(**given)
    with pytest.raises(jbus.Refused, match="top-level blocking_"):
        jbus.load()


def test_the_second_pair_is_secret(kitchen, second):
    relayed(kitchen, second)
    secret = jbus.load().secrets()
    assert SECOND_KEY in secret and second.url + "/relay" in secret
