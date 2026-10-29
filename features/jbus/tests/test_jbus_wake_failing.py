"""A home thread that keeps refusing its wakes reaches the user by a path that does not need it.

The refusal keeps the error text T3 Code gives. Each alert and recovered line goes to the journal
(the pass's `say`). The alert is the machine's, since the home it is about cannot hear it, so it
goes to the desk and the infra home, and this kitchen has no infra project. `jbus status`, the
heartbeat (`test_jbus_alive.py`, the one module with it on) and `jbus wakes` name the failing home
thread on a line of its own.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import timedelta

import jbus
from jbus import alert as alerts
from jbus import passes, wakes
from jsettings.t3 import T3Error
from test_jbus_kitchen import NOW, REFUSED

WHY = f"T3 Code did not take the wake: t3_thread_send: {REFUSED}"


def alert(count):
    return f"alert: home thread demo failed {count} times in a row since 11:00 ET: {WHY}"


def later(minutes):
    return NOW + timedelta(minutes=minutes)


OWNED = "report demo: the weekly CI report is ready"


def refusing(kitchen):
    """Have an alert of the project's open, and the project's home thread refuse its wakes."""
    ends = (NOW + timedelta(days=1)).isoformat()
    alerts.raise_(jbus.load(), "once report", OWNED, owner="demo", now=NOW, ends=ends)
    kitchen.wakes.refused = REFUSED


def fail(kitchen, passes, start=0):
    """Run passes five minutes apart, each with one wake that the home thread does not take."""
    said = []
    for number in range(start, start + passes):
        said += kitchen.poll(later(5 * number))
    return said


def test_a_refusal_keeps_the_error_text_in_the_journal_and_in_last_error(kitchen):
    refusing(kitchen)
    said = fail(kitchen, 3)
    assert [line for line in said if line.startswith("wait demo: ") and REFUSED in line]
    assert kitchen.status()["projects"]["demo"]["last_error"] == WHY


def test_the_alert_and_the_recovered_line_are_written_to_the_journal_and_the_desk(kitchen):
    refusing(kitchen)
    said = fail(kitchen, 3)
    assert said.count(f"demo: {alert(3)}") == 1
    assert kitchen.log("notify") == [f"jbus | {alert(3)}"]
    kitchen.wakes.refused = ""
    said = kitchen.poll(later(30))
    assert "demo: recovered: home thread demo after 3 failures since 11:00 ET" in said
    assert kitchen.wakes.said == [OWNED]


def test_status_names_the_failing_home_thread_as_an_alert_until_it_recovers(kitchen):
    refusing(kitchen)
    fail(kitchen, 3)
    code, said = kitchen.main("status")
    assert code == 0 and json.loads(said)["alerts"] == [alert(3)]
    assert kitchen.status()["alerts"] == [alert(3)]
    kitchen.wakes.refused = ""
    kitchen.poll(NOW + timedelta(hours=1, minutes=10))
    assert json.loads(kitchen.main("status")[1])["alerts"] == []


def test_jbus_wakes_says_whether_the_project_s_wakes_fail(kitchen):
    assert kitchen.main("wakes") == (0, "wakes go: the home thread of demo is not failing\n")
    refusing(kitchen)
    fail(kitchen, 2)
    assert kitchen.main("wakes") == (0, "wakes go: the home thread of demo is not failing\n")
    fail(kitchen, 1, start=2)
    assert kitchen.main("wakes") == (1, f"wakes fail: {alert(3)}\n")


def test_with_no_home_thread_no_wake_fails(kitchen):
    kitchen.config(home_thread=None)
    refusing(kitchen)
    said = fail(kitchen, 3)
    assert not [line for line in said if "alert:" in line]
    assert kitchen.main("wakes")[0] == 0


def test_a_wake_another_thread_refuses_counts_that_threads_own_streak(kitchen, monkeypatch):
    """A project's list reaches its root home and other threads, such as a child home's. Each has
    its own streak, so the root's success does not end a child's alert, and the child's failure
    is not the root's."""
    config = jbus.load()
    run = passes.Pass(config, config.project("demo"), NOW)
    root, child = wakes.root_of(run), "mcp:a-child-home"

    def send(run, client, *, thread, **_):
        if thread == child:
            raise T3Error(REFUSED)
        return True

    monkeypatch.setattr(wakes.outbox, "send", send)
    for to in (child, root) * 3:
        wakes._send(run, None, to, [wakes.Item(key="k", to=to, line="a line")])
    assert root and set(alerts.streaks(kitchen.state_dir)) == {alerts.home("demo", child)}
    assert alerts.streak(kitchen.state_dir, alerts.home("demo", child)).alerted
