"""When jbus is dead or failing, the user finds out. A failure in one project does not stop the
pass, and the pass always writes the status file. A `jmerge` command cannot hang. When the unit
fails for the third time in a row, jbus alerts once, through the webhook and the desk. Every hour,
the first pass queues a heartbeat, which is quiet: it starts no POST.

Every test runs the real pass or the real command against the faked T3 Code server and webhook of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
import jmerge.cli
from jbus import alive, cli, wake
from test_jbus_kitchen import KEY, NOW, PROJECT
from test_jbus_wake_failing import alert, fail, refusing

FAILED = (
    "alert: pass failed 3 times in a row since 11:00 ET: "
    "the last pass did not finish (see journalctl --user -u jbus)"
)


def decide(kitchen):
    """Queue one decision, the kind of event that starts a POST for the user."""
    box = wake.Box(kitchen.state, jbus.load().project("demo"), jbus.load().webhook)
    box.send("alpha", "decision", "decision alpha: which one?")


def test_a_project_that_raises_does_not_end_the_pass_and_the_status_is_still_written(kitchen):
    """The state path of `broken` is a file, so its part of the pass raises. `demo` comes after
    it."""
    decide(kitchen)
    path = kitchen.config_dir / "config.toml"
    top, demo = path.read_text().split("[[project]]", 1)
    broken = [
        "[[project]]",
        'name = "broken"',
        f"checkout = {json.dumps(str(kitchen.checkout))}",
        'state = "demo"',
        f"projectId = {json.dumps(PROJECT)}",
    ]
    kitchen.write(path, top + "\n".join(broken) + "\n[[project]]" + demo)
    (kitchen.state_dir / "broken").write_text("a file where the state directory goes\n")
    said = []
    assert cli.poll(jbus.load(), NOW, said.append) == 1
    (failed,) = [line for line in said if line.startswith("pass failed")]
    assert failed.startswith("pass failed broken: FileExistsError: ")
    assert "woke demo: 1 events" in said
    assert "wait: crews out not known (broken: the pass raised)" in said
    assert "decision alpha: which one?" in [
        e["line"] for post in kitchen.webhook.posts for e in post
    ]
    status = kitchen.status()
    assert status["projects"]["broken"]["last_error"] == failed.removeprefix("pass failed broken: ")
    assert status["projects"]["demo"]["last_error"] == ""
    assert status["last_pass"] == "2026-10-12 11:00 ET"


def test_a_pass_where_nothing_raised_exits_zero(kitchen):
    assert cli.poll(jbus.load(), NOW, lambda _: None) == 0
    assert kitchen.main("poll")[0] == 0


def test_a_jmerge_command_that_hangs_is_a_failed_command_after_the_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("JMERGE_TIMEOUT", "1")
    ran = jmerge.cli._run(tmp_path, "sleep", "5")
    assert (ran.returncode, ran.stderr) == (124, "timed out after 1 s: sleep 5")
    assert jmerge.cli._said(ran) == "timed out after 1 s: sleep 5"
    monkeypatch.delenv("JMERGE_TIMEOUT")
    assert jmerge.cli.TIMEOUT_SECONDS == 120
    done = jmerge.cli._run(tmp_path, "echo", "ran")
    assert (done.returncode, done.stdout) == (0, "ran\n")


def alarm(now):
    said = []
    assert alive.alarm(jbus.load(), now, said.append) == 0
    return said


def test_the_third_alarm_in_a_row_alerts_once_and_never_shows_the_webhook(kitchen):
    said = alarm(NOW) + alarm(NOW + timedelta(minutes=1))
    assert said == ["pass failed: 1 in a row", "pass failed: 2 in a row"]
    assert kitchen.events() == [] and kitchen.log("notify") == []
    said += alarm(NOW + timedelta(minutes=2)) + alarm(NOW + timedelta(hours=1))
    assert said[2:] == [
        "pass failed: 3 in a row",
        f"demo: {FAILED}",
        "alert sent: demo",
        "pass failed: 4 in a row",
    ]
    events = [event for post in kitchen.webhook.posts for event in post]
    assert [(e["project"], e["slug"], e["event"], e["line"]) for e in events] == [
        ("demo", "", "alert", FAILED)
    ]
    assert kitchen.webhook.said == [[f"demo: {FAILED}"]] and kitchen.webhook.keys == [KEY]
    assert kitchen.log("notify") == [f"jbus | {FAILED}"]
    assert not [line for line in said if KEY in line or kitchen.webhook.url in line]


def test_an_alert_the_webhook_did_not_take_waits_and_a_pass_keeps_the_streaks(kitchen):
    """The test runs the command as the unit runs it. What the command could not send goes out
    with the next flush."""
    kitchen.webhook.status = 500
    assert [kitchen.main("alarm") for _ in range(2)] == [
        (0, "pass failed: 1 in a row\n"),
        (0, "pass failed: 2 in a row\n"),
    ]
    code, said = kitchen.main("alarm")
    (line,) = [one for one in said.splitlines() if one.startswith("demo: alert: pass failed 3 ")]
    assert (code, said) == (
        0,
        f"pass failed: 3 in a row\n{line}\nwake failed demo: the webhook answered 500\n"
        "alert waits: demo\n",
    )
    assert kitchen.webhook.url not in said and KEY not in said
    (alert,) = kitchen.lines("alert")
    assert alert.startswith("alert: pass failed 3 times in a row since ")
    streaks = jbus.read_json(kitchen.state_dir / "streaks.json", {})
    assert (streaks["pass"]["count"], streaks["pass"]["alerted"]) == (3, True)
    assert (streaks["webhook demo"]["count"], streaks["webhook demo"]["alerted"]) == (1, False)
    kitchen.webhook.status = 200
    kitchen.poll(datetime.now(UTC) + timedelta(minutes=1))
    assert kitchen.status()["streaks"] == {"webhook demo": streaks["webhook demo"]}
    assert kitchen.webhook.posts == []
    kitchen.poll(datetime.now(UTC) + timedelta(minutes=6))
    assert kitchen.status()["streaks"] == {}
    assert kitchen.webhook.said == [[f"demo: {alert}"]]
    (recovered,) = kitchen.lines("recovered")
    assert recovered.startswith("recovered: pass after 3 failures ")
    assert kitchen.log("notify") == [f"jbus | {alert}", f"jbus | {recovered}"]


STALE = (
    "alert: stale failed 1 times in a row since {since}: "
    "no pass ended since {last}, more than 2h ago"
)


def stale(now, limit="2h"):
    said = []
    assert alive.stale(jbus.load(), alive.span(limit), now, said.append) == 0
    return said


def test_no_pass_for_two_hours_alerts_once_and_the_next_pass_logs_that_it_recovered(kitchen):
    """Its own timer runs the watcher, `jbus alarm --stale 2h`. The watcher reads the end of the
    last pass from `pass.json`, and the first pass after the outage ends the alarm's stale
    streak."""
    kitchen.poll(NOW)
    assert stale(NOW + timedelta(hours=1, minutes=59)) == ["pass seen: last ended 11:00 ET"]
    assert kitchen.webhook.posts == [] and kitchen.log("notify") == []
    first = STALE.format(since="13:01 ET", last="2026-10-12 11:00 ET")
    assert stale(NOW + timedelta(hours=2, minutes=1)) == [
        "no pass: last ended 2026-10-12 11:00 ET",
        f"demo: {first}",
        "alert sent: demo",
    ]
    assert stale(NOW + timedelta(hours=3)) == ["no pass: last ended 2026-10-12 11:00 ET"]
    assert kitchen.webhook.said == [[f"demo: {first}"]]
    assert kitchen.log("notify") == [f"jbus | {first}"]
    kitchen.poll(NOW + timedelta(hours=3, minutes=10))
    recovered = "recovered: stale after 2 failures since 13:01 ET"
    assert (kitchen.lines("alert"), kitchen.lines("recovered")) == ([first], [recovered])
    assert kitchen.status()["streaks"] == {}
    kitchen.poll(NOW + timedelta(hours=3, minutes=11))
    assert kitchen.webhook.said == [[f"demo: {first}"]]
    assert (kitchen.lines("alert"), kitchen.lines("recovered")) == ([first], [recovered])
    second = STALE.format(since="16:12 ET", last="2026-10-12 14:11 ET")
    assert stale(NOW + timedelta(hours=5, minutes=12))[1:] == [
        f"demo: {second}",
        "alert sent: demo",
    ]
    assert kitchen.webhook.said[1:] == [[f"demo: {second}"]]
    assert kitchen.log("notify")[1:] == [f"jbus | {second}"]


def test_a_pass_that_never_ended_counts_from_its_start_and_no_record_is_no_pass(kitchen):
    alert = "alert: stale failed 1 times in a row since 11:00 ET: no pass on record"
    assert stale(NOW) == ["no pass: none on record", f"demo: {alert}", "alert sent: demo"]
    assert kitchen.lines("alert") == [alert]
    jbus.write_json(kitchen.state_dir / "pass.json", {"started": "2026-10-12T15:00:00Z"})
    assert stale(NOW + timedelta(minutes=1), "1m") == ["pass seen: last ended 11:00 ET"]
    assert stale(NOW + timedelta(minutes=2), "1m") == ["no pass: last ended 2026-10-12 11:00 ET"]


def test_the_alarm_verb_takes_a_limit_in_minutes_hours_or_days(kitchen):
    kitchen.poll(datetime.now(UTC))
    code, said = kitchen.main("alarm", "--stale", "2h")
    assert (code, said.startswith("pass seen: last ended ")) == (0, True)
    code, said = kitchen.main("alarm", "--stale", "2x")
    assert code == 2 and "a limit is a number and m, h or d, as 2h: not 2x" in said
    assert [alive.span(given) for given in ("15m", "2h", "1d")] == [
        timedelta(minutes=15),
        timedelta(hours=2),
        timedelta(days=1),
    ]
    assert kitchen.main("alarm") == (0, "pass failed: 1 in a row\n")


def test_the_first_pass_of_each_hour_queues_one_heartbeat_which_starts_no_post(kitchen):
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=59))
    assert kitchen.lines("heartbeat") == [
        "heartbeat: jbus alive, last pass none, failed wakes 0, last error none"
    ]
    assert kitchen.webhook.posts == [] and kitchen.waiting() == []
    kitchen.webhook.status = 500
    decide(kitchen)
    kitchen.poll(NOW + timedelta(minutes=59, seconds=30))
    kitchen.webhook.status = 200
    kitchen.poll(NOW + timedelta(hours=1))
    assert kitchen.lines("heartbeat")[1:] == [
        "heartbeat: jbus alive, last pass 11:59 ET, failed wakes 1, "
        "last error the webhook answered 500"
    ]
    (heartbeat,) = [e for e in kitchen.events("heartbeat") if "11:59" in e["line"]]
    assert (heartbeat["slug"], heartbeat["loud"], heartbeat["posted"]) == ("", "quiet", None)
    assert "woke demo: 1 events" in kitchen.poll(NOW + timedelta(hours=1, minutes=5))
    assert [e["event"] for e in kitchen.webhook.posts[0]] == ["decision"]
    assert kitchen.webhook.said == [["demo: decision alpha: which one?"]]
    assert [one["posted"] for one in kitchen.events("heartbeat")] == [None, None]


@pytest.mark.parametrize(
    "url", ["example.test/abc?key=SECRET", "http://example.test/a b?key=SECRET"]
)
def test_a_webhook_url_that_cannot_be_used_is_in_no_line_and_not_in_the_status(kitchen, url):
    kitchen.config(url=url)
    decide(kitchen)
    said = []
    assert cli.poll(jbus.load(), NOW, said.append) == 1
    assert alive.alarm(jbus.load(), NOW + timedelta(minutes=6), said.append) == 1
    assert cli.poll(jbus.load(), NOW + timedelta(hours=1), said.append) == 1
    failed = [line for line in said if "failed demo: " in line]
    assert [line.split(":")[0] for line in failed] == ["pass failed demo", "alarm failed demo"] + [
        "pass failed demo"
    ]
    assert all("[webhook]" in line for line in failed)
    written = "\n".join([*said, *kitchen.lines(), (kitchen.state_dir / "status.json").read_text()])
    assert kitchen.status()["projects"]["demo"]["last_error"].count("[webhook]") >= 1
    assert len(kitchen.lines("heartbeat")) == 2 and "[webhook]" in kitchen.lines("heartbeat")[1]
    for part in ("SECRET", "example.test", "/abc", "/a b", KEY):
        assert part not in written


def test_the_heartbeat_names_a_failing_webhook_as_an_alert_on_a_line_of_its_own(kitchen):
    refusing(kitchen)
    fail(kitchen, 3)
    kitchen.poll(NOW + timedelta(hours=1))
    (beat, alarm) = kitchen.lines("heartbeat")[1:]
    assert beat.startswith("heartbeat: jbus alive, ") and alarm == alert(3)
