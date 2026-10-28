"""A home thread that keeps refusing its wakes reaches the user by a path that does not need it.

The refusal keeps the error text T3 Code gives. Each alert and recovered line goes to the journal
(the pass's `say`), and the alert to the desk. `jbus status`, the heartbeat (`test_jbus_alive.py`,
the one module with it on) and `jbus wakes` name the failing home thread on a line of its own.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import timedelta

from test_jbus_kitchen import NOW, REFUSED
from test_jbus_signal import decide, later

WHY = f"T3 Code did not take the wake: t3_thread_send: {REFUSED}"


def alert(count):
    return f"alert: home thread demo failed {count} times in a row since 11:00 ET: {WHY}"


def refusing(kitchen):
    """Have a decision wait, and the project's home thread refuse its wakes."""
    decide(kitchen)
    kitchen.wakes.refused = REFUSED


def fail(kitchen, passes, start=0):
    """Run passes five minutes apart, each with one wake that the home thread does not take."""
    said = []
    for number in range(start, start + passes):
        said += kitchen.poll(later(5 * number))
    return said


def test_a_refusal_keeps_the_error_text_in_the_journal_and_in_last_error(kitchen):
    refusing(kitchen)
    said = kitchen.poll(NOW)
    assert f"wake failed demo home thread: {WHY}" in said
    assert kitchen.marks()["last_error"] == WHY
    assert kitchen.status()["projects"]["demo"]["last_error"] == WHY


def test_the_alert_and_the_recovered_line_are_written_to_the_journal_and_the_desk(kitchen):
    refusing(kitchen)
    said = fail(kitchen, 3)
    assert said.count(f"demo: {alert(3)}") == 1
    assert kitchen.log("notify") == [f"jbus | {alert(3)}"]
    kitchen.wakes.refused = ""
    said = kitchen.poll(later(30))
    assert "demo: recovered: home thread demo after 3 failures since 11:00 ET" in said
    assert [event["line"] for event in kitchen.wakes.posts[0]] == [
        "decision alpha: which one?",
        alert(3),
    ]


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
