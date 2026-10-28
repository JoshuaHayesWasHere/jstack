"""A project's wakes go to its home thread through T3 Code, and nowhere else.

A wake to the home thread is one `t3_thread_send` in queue mode, with the chat lines and the events
(`wake.body`) and a retry key made from that body, so a retry sends the same message. It keeps a
five-minute gap. A send T3 Code refuses keeps the events in the outbox for the next pass, and its
streak alerts in the journal and on the desk. A wake to a home thread whose instance is capped waits
in the outbox for the reset, and counts as no failed send.

A config from before, with `wake`, `webhook_url` or `webhook_key`, loads as this one route and posts
nothing. What an old webhook outbox still holds moves to the home thread's, and the old webhook's
streaks end on the next pass with no line.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
import socket
from datetime import timedelta

import pytest

import jbus
from jbus import alert, blockers, wake
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


def listener():
    """A socket that listens and is never read, so that a post to it would be seen."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(0)
    return server


def old_config(kitchen, url):
    """Write a config from before: `wake = "both"` and a webhook pair at the top and in the
    project's table."""
    pair = [f"webhook_url = {json.dumps(url)}", 'webhook_key = "an-old-key"']
    kitchen.config(own=['wake = "both"', *pair], wake="both")
    path = kitchen.config_dir / "config.toml"
    first, rest = path.read_text().split("\n", 1)
    path.write_text("\n".join([first, *pair, rest]))


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


def test_an_old_config_with_wake_both_and_a_webhook_url_loads_as_home_and_posts_nothing(kitchen):
    server = listener()
    try:
        url = f"http://127.0.0.1:{server.getsockname()[1]}/wake"
        old_config(kitchen, url)
        decide(kitchen)
        config = jbus.load()
        assert config.ignored == (
            "wake at the top",
            "webhook_url at the top",
            "webhook_key at the top",
            "wake of project demo",
            "webhook_url of project demo",
            "webhook_key of project demo",
        )
        said = kitchen.poll(NOW)
        assert len(wakes(kitchen)) == 1
        try:
            server.accept()
            posted = True
        except BlockingIOError:
            posted = False
        assert not posted
        assert url not in "\n".join(said) and "an-old-key" not in "\n".join(said)
    finally:
        server.close()


def test_a_webhook_streak_from_before_is_gone_after_one_pass_with_no_line(kitchen):
    homed(kitchen)
    old = {
        key.format("demo"): {
            "key": key.format("demo"),
            "count": 148,
            "since": NOW.isoformat(),
            "alerted": True,
            "paged": True,
        }
        for key in alert.OLD
    }
    other = {"key": "other", "count": 1, "since": NOW.isoformat(), "alerted": False}
    jbus.write_json(kitchen.state_dir / "streaks.json", {**old, "other": other})
    said = kitchen.poll(NOW)
    kept = jbus.read_json(kitchen.state_dir / "streaks.json", {})
    assert not [key for key in kept if "webhook" in key]
    assert kept["other"] == other
    assert not [one for one in said if "webhook" in one]
    assert not [line for line in kitchen.lines() if "webhook" in line]
    code, status = kitchen.main("status")
    assert code == 0 and "webhook" not in status


def test_what_an_old_webhook_outbox_holds_reaches_the_home_thread_once(kitchen):
    """2026-10-23: decisions waited for the own webhook under `wake = "webhook"`, the webhook
    refused them, and `wake = "home"` left them in that outbox for good."""
    kitchen.config()
    decide(kitchen)
    decide_again(kitchen)
    held = waiting(kitchen)
    jbus.write_json(kitchen.state / "outbox.json", held)
    jbus.write_json(kitchen.state / wake.HOME / "outbox.json", held[:1])
    (kitchen.state / "top-level").mkdir()
    jbus.write_json(kitchen.state / "top-level" / "outbox.json", held[1:])
    jbus.write_json(kitchen.state / "unposted.json", {"told": []})
    said = kitchen.poll(NOW)
    lines = sent_events(kitchen)
    assert lines.count("decision alpha: which one?") == 1
    assert lines.count("decision beta: ?") == 1
    assert waiting(kitchen) == []
    assert not (kitchen.state / "outbox.json").exists()
    assert not (kitchen.state / "top-level").exists()
    assert not (kitchen.state / "unposted.json").exists()
    assert (
        "moved demo: 1 events for the user from the old webhook's outbox to the home thread's"
        in said
    )
    again = kitchen.poll(later(10))
    assert sent_events(kitchen) == lines
    assert not any(one.startswith("moved demo") for one in again)


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
