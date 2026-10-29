"""A project's wakes go to its home thread through T3 Code, and nowhere else.

A wake to the home thread is one `t3_thread_send` in queue mode, with the chat lines and the events
(`wake.body`) and a retry key made from that body, so a retry sends the same message. It keeps a
five-minute gap. A send T3 Code refuses keeps the events in the outbox for the next pass, and its
streak alerts in the journal and on the desk. A wake to a home thread whose instance is capped waits
in the outbox for the reset, and counts as no failed send.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import blockers, wake
from jroles import ledger
from test_jbus_kitchen import HOME, NOW
from test_jbus_signal import decide, later

TOP = "mcp:top-home"


def wakes(kitchen, thread=HOME):
    """What the thread was sent as wakes, in order."""
    return [given for given in kitchen.t3.woken.values() if given["threadId"] == thread]


def waiting(kitchen):
    """What waits for the home thread."""
    return jbus.read_json(kitchen.state / wake.HOME / "outbox.json", [])


def homed(kitchen, **config):
    """Write the config with these settings, and have a decision wait."""
    kitchen.config(**config)
    decide(kitchen)


def sent_events(kitchen):
    """Each event the home thread was sent, by its line, in order."""
    return [one["line"] for post in kitchen.wakes.posts for one in post]


def decide_again(kitchen):
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).send("beta", "decision", "decision beta: ?")


def test_the_event_reaches_the_home_thread(kitchen):
    homed(kitchen)
    said = kitchen.poll(NOW)
    (sent,) = wakes(kitchen)
    assert sent["mode"] == "queue"
    assert "demo: decision alpha: which one?" in sent["message"]
    body = json.loads(sent["message"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert body["kind"] == "events" and body["say"] == ["demo: decision alpha: which one?"]
    assert [one["event"] for one in body["events"]] == ["decision"]
    assert "woke demo: 1 events" in said


@pytest.mark.parametrize("listed", [False, True], ids=["jbus decide", "an item of the list"])
def test_a_decision_reaches_the_home_thread_as_an_event_unless_the_one_list_carries_it(
    kitchen, listed
):
    """The review of #585: a decision `jbus decide`, `jbus clear` or a fix past its retry cap
    raises is on no list, so the home thread gets its event. One of an item on the list does
    not, since the list wakes the home with it."""
    homed(kitchen)
    kitchen.poll(NOW)
    before = len(wakes(kitchen))
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    blockers.decide(box, "beta", "beta-key", "which way?", "this way", listed=listed)
    kitchen.poll(later(10))
    told = [one["message"] for one in wakes(kitchen)[before:]]
    assert any("decision beta: which way?" in one for one in told) is not listed


def test_the_webhook_marks_from_before_leave_wake_json_on_the_next_pass(kitchen):
    homed(kitchen)
    marks = kitchen.state / "wake.json"
    old = {"began": True, "last_error": "the config has no webhook_url", "posted": 1.0}
    jbus.write_json(marks, {**old, "failed": 3, "alerted": True})
    kitchen.poll(NOW)
    assert jbus.read_json(marks, {}) == {"began": True}


def test_a_retry_after_a_lost_answer_keeps_one_message(kitchen):
    homed(kitchen)
    kitchen.t3.lose_send = True
    kitchen.poll(NOW)
    assert len(waiting(kitchen)) == 1
    kitchen.t3.lose_send = False
    kitchen.t3.woken.clear()
    kitchen.poll(later(5))
    kitchen.poll(later(10))
    (first,) = wakes(kitchen)
    assert waiting(kitchen) == []
    keys = [given["clientRequestId"] for tool, given in kitchen.t3.calls if tool.endswith("_send")]
    assert {key for key in keys if key.startswith("wake|")} == {first["clientRequestId"]}


def test_the_home_thread_gets_at_most_one_wake_in_five_minutes(kitchen):
    homed(kitchen)
    kitchen.poll(NOW)
    decide_again(kitchen)
    kitchen.poll(later(2))
    assert len(wakes(kitchen)) == 1
    kitchen.poll(later(5))
    assert len(wakes(kitchen)) == 2


def test_t3_refusing_keeps_the_events_and_alerts_in_the_journal_and_on_the_desk(kitchen):
    homed(kitchen)
    kitchen.t3.refuse_send = True
    said = []
    for number in range(3):
        said += kitchen.poll(later(5 * number))
    assert wakes(kitchen) == []
    assert any(one["event"] == "decision" for one in waiting(kitchen))
    line = next(one for one in said if one.startswith("demo: alert: home thread demo failed 3"))
    assert f"jbus | {line.removeprefix('demo: ')}" in kitchen.log("notify")
    code, printed = kitchen.main("wakes")
    assert code == 1 and printed.startswith("wakes fail: alert: home thread demo failed 3")
    kitchen.t3.refuse_send = False
    said = kitchen.poll(later(20))
    (sent,) = wakes(kitchen)
    assert "decision alpha" in sent["message"]
    assert any(one.startswith("demo: recovered: home thread demo") for one in said)
    assert kitchen.main("wakes") == (0, "wakes go: the home thread of demo is not failing\n")


def test_the_home_s_own_thread_gets_the_wake_before_the_top_level_home_thread(kitchen):
    (kitchen.home / "home-id").write_text(f"{TOP}\n")
    homed(kitchen)
    kitchen.poll(NOW)
    assert len(wakes(kitchen, TOP)) == 1 and wakes(kitchen) == []


def test_with_no_thread_at_all_the_events_wait_and_the_journal_says_so_once(kitchen):
    homed(kitchen, home_thread=None)
    said = kitchen.poll(NOW) + kitchen.poll(later(5))
    assert len([one for one in said if "no home thread" in one]) == 1
    assert waiting(kitchen) and kitchen.main("wakes")[0] == 0


def test_status_names_no_webhook_and_no_wake_setting(kitchen):
    homed(kitchen)
    kitchen.poll(NOW)
    status = kitchen.status()
    assert "webhook" not in json.dumps(status)
    assert "wake" not in status["projects"]["demo"]


def test_status_and_the_digest_show_the_last_sweep(kitchen):
    from jbus import digest, record

    homed(kitchen)
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).swept("2026-10-23 ran", True)
    assert record.status(config, NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"
    assert digest.build(config, now=NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"


def test_an_event_of_the_machine_reaches_the_home_thread(kitchen):
    homed(kitchen)
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.send("", "alert", "alert: the machine's own", machine=True)
    kitchen.poll(NOW)
    assert any("alert: the machine's own" in one["message"] for one in wakes(kitchen))


def test_an_event_the_home_thread_took_shows_as_posted(kitchen):
    homed(kitchen)
    kitchen.poll(NOW)
    assert len(wakes(kitchen)) == 1
    (decision,) = kitchen.events("decision")
    assert decision["posted"] is not None


def test_each_event_for_the_user_reaches_the_home_thread(kitchen):
    homed(kitchen)
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    for kind in ("sign-in", "home-stall", "alert"):
        box.send(kind, kind, f"demo: {kind} now")
    kitchen.poll(NOW)
    (sent,) = wakes(kitchen)
    body = json.loads(sent["message"].split("```json\n", 1)[1].split("\n```", 1)[0])
    kinds = {"decision", "sign-in", "home-stall", "alert"}
    assert {one["event"] for one in body["events"]} == kinds


def test_a_wake_to_a_capped_home_thread_waits_with_no_alert_and_goes_once_after_the_reset(kitchen):
    homed(kitchen)
    kitchen.t3.thread("home", "running")["threadId"] = HOME
    resets = NOW + timedelta(minutes=20)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    said = []
    for number in range(4):
        said += kitchen.poll(later(5 * number))
    assert wakes(kitchen) == []
    assert [one["event"] for one in waiting(kitchen)] == ["decision"]
    assert [one for one in said if "alert:" in one or "wake failed" in one] == []
    kitchen.poll(later(25))
    kitchen.poll(later(35))
    (sent,) = wakes(kitchen)
    assert "demo: decision alpha: which one?" in sent["message"]
    assert waiting(kitchen) == []
