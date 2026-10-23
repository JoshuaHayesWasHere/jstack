"""A webhook that keeps failing reaches the user by a path that does not need it.

The kitchen's project sends its wakes to its webhook alone (`wake = "webhook"`). The webhook's
refusal keeps the `error` text its JSON body gives. Each alert and recovered line goes to the
journal (the pass's `say`). While a project's webhook streak alerts, jbus tells the project's home
thread through T3 Code, at the third failure, the thirtieth, and every 120th after that.
`jbus status`, the heartbeat (`test_jbus_alive.py`, the one module with it on) and `jbus wakes`
name the failing webhook on a line of its own.

Every test runs the real pass or the real command against the faked T3 Code server and webhook of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import timedelta

import jbus
from test_jbus_kitchen import NOW
from test_jbus_signal import decide, later

HOME = "mcp:home-of-demo"
DISABLED = {"success": False, "error": "Automation wake-chef is disabled"}
WHY = "the webhook answered 400: Automation wake-chef is disabled"


def alert(count):
    return f"alert: webhook demo failed {count} times in a row since 11:00 ET: {WHY}"


def refusing(kitchen):
    """Have a decision wait, the project's home have a thread, and the webhook answer 400."""
    decide(kitchen)
    (kitchen.home / "home-id").write_text(HOME + "\n")
    kitchen.webhook.status, kitchen.webhook.refused = 400, DISABLED


def fail(kitchen, passes, start=0):
    """Run passes five minutes apart, each with one POST that the webhook does not take."""
    said = []
    for number in range(start, start + passes):
        said += kitchen.poll(later(5 * number))
    return said


def pages(kitchen):
    """What the home thread was sent, in order."""
    return [
        given["message"]
        for given in kitchen.t3.messages.values()
        if given["threadId"] == HOME and given["message"].startswith("jbus: alert:")
    ]


def counted(kitchen, count):
    """Set the webhook streak's count, as that many failed posts would have left it."""
    path = kitchen.state_dir / "streaks.json"
    streaks = jbus.read_json(path, {})
    streaks["webhook demo"]["count"] = count
    jbus.write_json(path, streaks)


def test_a_400_keeps_the_error_text_in_the_journal_and_in_last_error(kitchen):
    refusing(kitchen)
    said = kitchen.poll(NOW)
    assert f"wake failed demo: {WHY}" in said
    assert kitchen.marks()["last_error"] == WHY
    assert kitchen.status()["projects"]["demo"]["last_error"] == WHY


def test_the_alert_and_the_recovered_line_are_written_to_the_journal(kitchen):
    refusing(kitchen)
    said = fail(kitchen, 3)
    assert said.count(f"demo: {alert(3)}") == 1
    kitchen.webhook.status = 200
    said = kitchen.poll(later(30))
    assert "demo: recovered: webhook demo after 3 failures since 11:00 ET" in said


def test_the_alert_reaches_the_home_thread_at_3_30_and_every_120_failures(kitchen):
    refusing(kitchen)
    fail(kitchen, 2)
    assert pages(kitchen) == []
    said = fail(kitchen, 2, start=2)
    (first,) = pages(kitchen)
    assert first.splitlines()[0] == f"jbus: {alert(3)}"
    assert "again at 30 failures" in first
    assert f"paged demo's home, thread {HOME}: {alert(3)}" in said
    assert kitchen.webhook.posts == []
    counted(kitchen, 28)
    fail(kitchen, 2, start=4)
    assert [one.splitlines()[0] for one in pages(kitchen)[1:]] == [f"jbus: {alert(30)}"]
    assert "again at 120 failures" in pages(kitchen)[1]
    for start, to in ((118, 120), (238, 240)):
        counted(kitchen, start)
        fail(kitchen, 3, start=start)
        assert pages(kitchen)[-1].splitlines()[0] == f"jbus: {alert(to)}"
    assert len(pages(kitchen)) == 4


def test_a_page_t3_code_refused_goes_on_the_next_pass(kitchen):
    refusing(kitchen)
    kitchen.t3.refuse_send = True
    said = fail(kitchen, 3)
    assert pages(kitchen) == [] and any(line.startswith("page failed demo:") for line in said)
    kitchen.t3.refuse_send = False
    fail(kitchen, 1, start=3)
    (page,) = pages(kitchen)
    assert page.splitlines()[0] == f"jbus: {alert(4)}"


def test_with_no_home_thread_nothing_is_paged_and_the_journal_still_has_the_alert(kitchen):
    refusing(kitchen)
    (kitchen.home / "home-id").unlink()
    said = fail(kitchen, 3)
    assert pages(kitchen) == [] and f"demo: {alert(3)}" in said


def test_status_names_the_failing_webhook_as_an_alert_until_it_recovers(kitchen):
    refusing(kitchen)
    fail(kitchen, 3)
    code, said = kitchen.main("status")
    assert code == 0 and json.loads(said)["alerts"] == [alert(3)]
    assert kitchen.status()["alerts"] == [alert(3)]
    kitchen.webhook.status = 200
    kitchen.poll(NOW + timedelta(hours=1, minutes=10))
    assert json.loads(kitchen.main("status")[1])["alerts"] == []


def test_jbus_wakes_says_whether_the_project_s_wakes_fail(kitchen):
    assert kitchen.main("wakes") == (0, "wakes go: the webhook of demo is not failing\n")
    refusing(kitchen)
    fail(kitchen, 2)
    assert kitchen.main("wakes") == (0, "wakes go: the webhook of demo is not failing\n")
    fail(kitchen, 1, start=2)
    assert kitchen.main("wakes") == (1, f"wakes fail: {alert(3)}\n")
