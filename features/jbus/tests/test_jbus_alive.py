"""When jbus is dead or failing, the user finds out. A failure in one project does not stop the
pass, and the pass always writes the status file. A `jmerge` command cannot hang. When the unit
fails for the third time in a row, jbus raises the machine's alert once: the desk hears of it at
once, and the infra home from the one list. Every hour, the first pass queues a heartbeat, which is
quiet: it starts no wake.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta

import jbus
import jmerge.cli
import jmerge.lines
from jbus import alert as alerts
from jbus import alive, poll, wake
from test_jbus_kitchen import KEY, NOW, PROJECT, REFUSED
from test_jbus_wake_failing import alert, fail, refusing

HOME = "home thread demo"
WHY = f"T3 Code did not take the wake: t3_thread_send: {REFUSED}"

FAILED = (
    "alert: pass failed 3 times in a row since 11:00 ET: "
    "the last pass did not finish (see journalctl --user -u jbus)"
)


DECIDE = "decision alpha: which one?"


def decide(kitchen):
    """Open one alert of the project's, an item the one list tells its home thread of."""
    ends = (NOW + timedelta(days=1)).isoformat()
    alerts.raise_(jbus.load(), "once which", DECIDE, owner="demo", now=NOW, ends=ends)


def told(said):
    """Say whether a pass told demo's home thread of an item of the one list."""
    return any(line.startswith("wakes demo: told") for line in said)


def logged(side, kind):
    """The lines of one kind in the log of the project `side`."""
    every = wake.Box(side.state, jbus.load().project(side.name)).log()
    return [one["line"] for one in every if one["event"] == kind]


def machine(kitchen, now):
    """The keys of the open alerts of the machine's."""
    open_ = alerts.open_items(kitchen.state_dir, now)
    return [one.key for one in open_ if one.owner == alerts.MACHINE]


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
    assert poll.poll(jbus.load(), NOW, said.append) == 1
    (failed,) = [line for line in said if line.startswith("pass failed")]
    assert failed.startswith("pass failed broken: FileExistsError: ")
    assert told(said)
    assert "wait: crews out not known (broken: the pass raised)" in said
    assert DECIDE in kitchen.wakes.said
    status = kitchen.status()
    assert status["projects"]["broken"]["last_error"] == failed.removeprefix("pass failed broken: ")
    assert status["projects"]["demo"]["last_error"] == ""
    assert status["last_pass"] == "2026-10-12 11:00 ET"


def test_a_pass_where_nothing_raised_exits_zero(kitchen):
    assert poll.poll(jbus.load(), NOW, lambda _: None) == 0
    assert kitchen.main("poll")[0] == 0


def test_a_jmerge_command_that_hangs_is_a_failed_command_after_the_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("JMERGE_TIMEOUT", "1")
    ran = jmerge.cli._run(tmp_path, "sleep", "5")
    assert (ran.returncode, ran.stderr) == (124, "timed out after 1 s: sleep 5")
    assert jmerge.lines.said(ran) == "timed out after 1 s: sleep 5"
    monkeypatch.delenv("JMERGE_TIMEOUT")
    assert jmerge.cli.TIMEOUT_SECONDS == 120
    done = jmerge.cli._run(tmp_path, "echo", "ran")
    assert (done.returncode, done.stdout) == (0, "ran\n")


def alarm(now):
    said = []
    assert alive.alarm(jbus.load(), now, said.append) == 0
    return said


def test_the_third_alarm_in_a_row_alerts_once_on_the_desk_and_never_shows_the_key(kitchen):
    said = alarm(NOW) + alarm(NOW + timedelta(minutes=1))
    assert said == ["pass failed: 1 in a row", "pass failed: 2 in a row"]
    assert kitchen.events() == [] and kitchen.log("notify") == []
    said += alarm(NOW + timedelta(minutes=2)) + alarm(NOW + timedelta(hours=1))
    assert said[2:] == ["pass failed: 3 in a row", FAILED, "pass failed: 4 in a row"]
    assert machine(kitchen, NOW + timedelta(hours=1)) == [alerts.PASS]
    assert kitchen.events() == [] and kitchen.wakes.said == []
    assert kitchen.log("notify") == [f"jbus | {FAILED}"]
    assert not [line for line in said if KEY in line]


def test_the_alarm_s_alert_reaches_the_infra_home_and_the_next_pass_ends_it(kitchen):
    """The test runs the command as the unit runs it."""
    infra = kitchen.second("infra")
    assert [kitchen.main("alarm") for _ in range(2)] == [
        (0, "pass failed: 1 in a row\n"),
        (0, "pass failed: 2 in a row\n"),
    ]
    code, said = kitchen.main("alarm")
    (line,) = [one for one in said.splitlines() if one.startswith("alert: pass failed 3 ")]
    assert (code, said) == (0, f"pass failed: 3 in a row\n{line}\n")
    assert KEY not in said
    assert logged(infra, "alert") == [line]
    kitchen.poll(datetime.now(UTC) + timedelta(minutes=6))
    assert kitchen.status()["streaks"] == {}
    (recovered,) = logged(infra, "recovered")
    assert recovered.startswith("recovered: pass after 3 failures ")
    assert kitchen.wakes.said == [] and kitchen.log("notify") == [f"jbus | {line}"]


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
    assert kitchen.wakes.said == [] and kitchen.log("notify") == []
    first = STALE.format(since="13:01 ET", last="2026-10-12 11:00 ET")
    assert stale(NOW + timedelta(hours=2, minutes=1)) == [
        "no pass: last ended 2026-10-12 11:00 ET",
        first,
    ]
    assert stale(NOW + timedelta(hours=3)) == ["no pass: last ended 2026-10-12 11:00 ET"]
    assert machine(kitchen, NOW + timedelta(hours=3)) == [alerts.STALE]
    assert kitchen.log("notify") == [f"jbus | {first}"]
    kitchen.poll(NOW + timedelta(hours=3, minutes=10))
    assert kitchen.status()["streaks"] == {}
    assert machine(kitchen, NOW + timedelta(hours=3, minutes=10)) == []
    kitchen.poll(NOW + timedelta(hours=3, minutes=11))
    assert kitchen.wakes.said == []
    second = STALE.format(since="16:12 ET", last="2026-10-12 14:11 ET")
    assert stale(NOW + timedelta(hours=5, minutes=12))[1:] == [second]
    assert kitchen.log("notify")[1:] == [f"jbus | {second}"]


def test_a_pass_that_never_ended_counts_from_its_start_and_no_record_is_no_pass(kitchen):
    alert = "alert: stale failed 1 times in a row since 11:00 ET: no pass on record"
    assert stale(NOW) == ["no pass: none on record", alert]
    assert kitchen.log("notify") == [f"jbus | {alert}"]
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
    assert kitchen.wakes.said == []
    kitchen.wakes.refused = REFUSED
    decide(kitchen)
    kitchen.poll(NOW + timedelta(minutes=59, seconds=30))
    kitchen.wakes.refused = ""
    kitchen.poll(NOW + timedelta(hours=1))
    assert kitchen.lines("heartbeat")[1:] == [
        f"heartbeat: jbus alive, last pass 11:59 ET, failed wakes 1, last error {WHY}"
    ]
    (heartbeat,) = [e for e in kitchen.events("heartbeat") if "11:59" in e["line"]]
    assert (heartbeat["slug"], heartbeat["loud"]) == ("", "quiet")
    assert kitchen.wakes.listed == [[DECIDE]]


def test_the_heartbeat_names_a_failing_home_thread_as_an_alert_on_a_line_of_its_own(kitchen):
    refusing(kitchen)
    fail(kitchen, 3)
    kitchen.poll(NOW + timedelta(hours=1))
    (beat, alarm) = kitchen.lines("heartbeat")[1:]
    assert beat.startswith("heartbeat: jbus alive, ") and alarm == alert(3)
