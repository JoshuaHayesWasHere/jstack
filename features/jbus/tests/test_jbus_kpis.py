"""Each KPI threshold sends one jbus alert when it is crossed, and none when it is not, and no KPI
of the page's registry says it lacks a row that has merged.

The tests write the records jbus writes, of two projects, `alpha` and `beta`, and T3 Code's store
of usage-limit failures, build the telemetry store, and run the pass's look at the thresholds
(`kpis.look`). What they read is what a home hears: the open alerts of the one list, and each
`alert` event the owning project logged. A threshold is a daily count, or for pass time a
percentile of the last hour, against its limit, and a crossing alerts once, however many passes
look at it.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
from jbus import alert, kpis, telemetry, wake

NOW = datetime(2026, 11, 2, 20, 0, tzinfo=UTC)
"""15:00 in New York, the user's zone: the local day began at 05:00 UTC."""
MIDNIGHT = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)


def iso(moment):
    return moment.isoformat(timespec="seconds")


class Machine:
    """A jbus config of `alpha`, the infra project, and `beta`, in New York."""

    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path
        config, self.state_dir, self.home_dir = (tmp_path / name for name in ("c", "s", "h"))
        lines = ['server = "http://127.0.0.1:1"', 'infra = "alpha"']
        for name in ("alpha", "beta"):
            (self.state_dir / name).mkdir(parents=True)
            (self.home_dir / name).mkdir(parents=True)
            lines += [
                "[[project]]",
                f'name = "{name}"',
                f'checkout = "{tmp_path / name}"',
                f'projectId = "{name}-id"',
            ]
        config.mkdir()
        (config / "config.toml").write_text("\n".join(lines) + "\n")
        (config / "config.toml").chmod(0o600)
        settings = tmp_path / "xdg" / "jstack"
        settings.mkdir(parents=True)
        (settings / "config.toml").write_text('timezone = "America/New_York"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("JBUS_CONFIG_DIR", str(config))
        monkeypatch.setenv("JBUS_STATE_DIR", str(self.state_dir))
        monkeypatch.setenv("JBUS_HOME_DIR", str(self.home_dir))
        monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
        self.desk: list[str] = []
        monkeypatch.setattr(wake, "notify", self.desk.append)

    def append(self, name, *lines, project=None):
        """Add JSON lines to a log as its writer does, a project's or the machine's."""
        folder = self.state_dir / project if project else self.state_dir
        with open(folder / name, "a") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")

    def look(self, now=NOW):
        """One pass's look: the store brought up to date, then the thresholds read."""
        config = jbus.load()
        telemetry.build(config)
        said: list[str] = []
        kpis.look(config, now, said.append)
        return said

    def alerts(self, now=NOW):
        """The open alerts a home hears of, each line."""
        return sorted(one.line for one in alert.open_items(self.state_dir, now))

    def logged(self, project):
        path = self.state_dir / project / "events.jsonl"
        if not path.exists():
            return []
        found = [json.loads(line) for line in path.read_text().splitlines()]
        return [one["line"] for one in found if one["event"] == "alert"]


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def door(at, kind="home", outcome="done", checked=False, doors=("deploy",)):
    """An act on a one-way door, as `jbus.acts` logs it."""
    return {
        "action": {"doors": list(doors), "subject": "row", "verb": "go"},
        "at": iso(at),
        "evidence": {"source": "typed", "ref": "thread/x", "checked": checked, "words": "go"},
        "id": f"act-{at.timestamp()}-{kind}-{checked}",
        "line": "go row",
        "outcome": outcome,
        "party": {"kind": kind, "name": "", "route": "cli"},
    }


def test_a_door_opened_without_the_users_word_alerts_on_one(machine):
    at = NOW - timedelta(hours=1)
    machine.append("acts.jsonl", door(at, kind="user", checked=True), project="alpha")
    machine.append("acts.jsonl", door(at, outcome="gated"), project="alpha")
    machine.append("acts.jsonl", door(at, outcome="done", doors=()), project="beta")
    machine.append("acts.jsonl", door(at, kind="home", checked=True), project="beta")

    assert machine.look() == []
    assert machine.alerts() == []

    machine.append("acts.jsonl", door(at, kind="bot"), project="beta")
    said = machine.look()

    line = (
        "alert: kpi doors beta: 1 one-way door opened on 2026-11-02 without the user's word, "
        "and the threshold alerts on 1"
    )
    assert said == [f"beta: {line}"]
    assert machine.alerts() == [line]
    assert machine.logged("beta") == [line]
    assert machine.logged("alpha") == []


def test_a_door_opened_yesterday_is_not_todays_count(machine):
    machine.append("acts.jsonl", door(MIDNIGHT - timedelta(minutes=1)), project="alpha")
    assert machine.look() == []
    assert machine.alerts() == []


def red(run, sha, conclusion, at):
    """A push check of main, as the CI ledger keeps its job."""
    return {
        "run": run,
        "job": run * 10,
        "attempt": 1,
        "name": "check",
        "sha": sha,
        "branch": "main",
        "event": "push",
        "created": iso(at - timedelta(minutes=5)),
        "completed": iso(at),
        "conclusion": conclusion,
    }


def test_a_red_main_raises_no_kpi_alert_however_long_it_is_red(machine):
    """jbus files a main-red row for every red tip (`jbus.watch.retro`), so a KPI alert of a
    red main would wake a home a second time for what the row already says (the user,
    2026-11-08: "jbus always files it")."""
    machine.append(
        "ci.jsonl",
        red(1, "a", "failure", MIDNIGHT - timedelta(minutes=50)),
        red(2, "b", "success", MIDNIGHT + timedelta(minutes=10)),
        red(3, "c", "failure", NOW - timedelta(hours=3)),
        project="alpha",
    )
    later = NOW + timedelta(minutes=1)
    assert machine.look(later) == []
    assert machine.alerts(later) == []


class T3:
    """T3 Code's store, with the usage-limit failures `jgauge spend` reads, and the threads and
    messages the store's `ask_ledger` reads."""

    def __init__(self, root):
        (root / "t3" / "userdata").mkdir(parents=True)
        self.db = sqlite3.connect(root / "t3" / "userdata" / "statev2.sqlite")
        self.db.executescript(
            "create table orchestration_v2_projection_runs (run_id text primary key, "
            "requested_at text, payload_json text, provider_instance_id text);"
            "create table orchestration_v2_projection_turn_items (turn_item_id text primary key, "
            "thread_id text, run_id text, type text, status text, payload_json text);"
            "create table orchestration_v2_projection_threads ("
            "thread_id text primary key, project_id text, payload_json text);"
            "create table orchestration_v2_projection_messages (message_id text primary key, "
            "thread_id text not null, role text not null, created_at text not null, "
            "payload_json text not null);"
        )
        self.runs = 0

    def thread(self, thread, project_id):
        self.db.execute(
            "insert into orchestration_v2_projection_threads values (?, ?, '{}')",
            (thread, project_id),
        )
        self.db.commit()

    def say(self, message, thread, at, role="user"):
        """A message of the thread: one the user typed, or the assistant's."""
        payload = {"text": "words", "createdBy": "user" if role == "user" else None}
        self.db.execute(
            "insert into orchestration_v2_projection_messages values (?, ?, ?, ?, ?)",
            (message, thread, role, at.strftime("%Y-%m-%dT%H:%M:%S.000Z"), json.dumps(payload)),
        )
        self.db.commit()

    def capped(self, instance, at, reset):
        """A Claude run of the instance that failed at `at` on a usage limit until `reset`."""
        self.runs += 1
        run = f"run{self.runs}"
        model = json.dumps({"modelSelection": {"model": "claude-opus-5-5"}})
        self.db.execute(
            "insert into orchestration_v2_projection_runs values (?, ?, ?, ?)",
            (run, iso(at), model, instance),
        )
        failure = {"startedAt": iso(at), "failure": {"class": "usage_limit", "resetAt": iso(reset)}}
        self.db.execute(
            "insert into orchestration_v2_projection_turn_items values (?, 't', ?, ?, ?, ?)",
            (f"{run}-error", run, "error", "failed", json.dumps(failure)),
        )
        self.db.commit()


def test_capped_minutes_alert_over_30_in_a_day_with_every_instance_capped(machine):
    t3 = T3(machine.root)
    t3.capped("one", NOW - timedelta(minutes=40), NOW + timedelta(hours=2))
    t3.capped("two", NOW - timedelta(minutes=30), NOW + timedelta(hours=1))

    assert machine.look() == []
    assert machine.alerts() == []

    later = NOW + timedelta(minutes=1)
    said = machine.look(later)

    line = (
        "alert: kpi capped: every instance capped 31 min on 2026-11-02, "
        "over the threshold of 30 min"
    )
    assert said == [line]
    assert machine.alerts(later) == [line]
    assert machine.logged("alpha") == [line]
    assert machine.desk == [line]


def test_one_instance_capped_all_day_is_no_capped_minute(machine):
    t3 = T3(machine.root)
    t3.capped("one", MIDNIGHT, NOW + timedelta(hours=2))
    t3.capped("two", NOW - timedelta(days=3), NOW - timedelta(days=3) + timedelta(minutes=5))
    assert machine.look() == []
    assert machine.alerts() == []


def passes(machine, seconds, since, every=timedelta(minutes=2)):
    """Each pass the record logged, one `every` from `since` up to NOW, each of `seconds`."""
    at = since
    while at <= NOW:
        machine.append("passes.jsonl", {"at": iso(at), "seconds": seconds(at)})
        at += every


def test_pass_time_alerts_when_the_hours_p90_is_over_60_seconds(machine):
    hour = NOW - timedelta(hours=1)
    passes(machine, lambda at: 61.0 if at.minute in (10, 30, 50) else 30.0, hour)
    old = (NOW - timedelta(hours=hours) for hours in (3, 2))
    machine.append("passes.jsonl", *({"at": iso(at), "seconds": 90.0} for at in old))

    assert machine.look() == []

    machine.append("passes.jsonl", {"at": iso(NOW), "seconds": 61.0})
    machine.append("passes.jsonl", {"at": iso(NOW), "seconds": 61.0})
    said = machine.look()

    line = (
        "alert: kpi pass-time: jbus's pass p90 61 s over the last hour, over the threshold of 60 s"
    )
    assert said == [line]
    assert machine.alerts() == [line]


def test_pass_time_needs_a_whole_hour_of_passes(machine):
    passes(machine, lambda at: 120.0, NOW - timedelta(minutes=50))
    assert machine.look() == []
    assert machine.alerts() == []


WAIT = timedelta(minutes=telemetry.schema.WAIT)


def test_a_lost_ask_today_alerts_once_however_many_passes_look(machine):
    t3 = T3(machine.root)
    t3.thread("mcp:alpha-home", "alpha-id")
    t3.thread("mcp:beta-home", "beta-id")
    t3.say("m-answered", "mcp:beta-home", NOW - 2 * WAIT)
    t3.say("r-answered", "mcp:beta-home", NOW - 2 * WAIT + timedelta(minutes=1), role="assistant")
    t3.say("m-lost", "mcp:alpha-home", NOW - 2 * WAIT)
    said = machine.look()

    line = (
        "alert: kpi lost-asks alpha: 1 ask lost on 2026-11-02, with no act citing it and no "
        "reply within 120 min, and the threshold alerts on 1"
    )
    assert said == [f"alpha: {line}"]
    assert machine.alerts() == [line]
    assert machine.logged("alpha") == [line]
    assert machine.logged("beta") == []

    t3.say("m-lost-too", "mcp:alpha-home", NOW - WAIT - timedelta(minutes=5))
    later = NOW + timedelta(minutes=1)
    assert machine.look(later) == []
    assert machine.look(later + timedelta(minutes=1)) == []
    assert machine.alerts(later) == [line]
    assert machine.logged("alpha") == [line]


def test_a_day_with_no_lost_ask_alerts_none(machine):
    t3 = T3(machine.root)
    t3.thread("mcp:alpha-home", "alpha-id")
    t3.say("m-yesterday", "mcp:alpha-home", MIDNIGHT - WAIT - timedelta(minutes=1))
    t3.say("m-today", "mcp:alpha-home", MIDNIGHT + timedelta(hours=1))
    t3.say("r-today", "mcp:alpha-home", MIDNIGHT + timedelta(hours=1, minutes=2), role="assistant")

    assert machine.look() == []
    assert machine.alerts() == []
    assert machine.logged("alpha") == []


def test_a_crossing_alerts_once_however_many_passes_look_and_its_number_moves(machine):
    at = NOW - timedelta(hours=1)
    machine.append("acts.jsonl", door(at), project="alpha")
    first = machine.look()
    machine.append("acts.jsonl", door(at + timedelta(minutes=5), kind="bot"), project="alpha")
    second = machine.look(NOW + timedelta(minutes=1))
    third = machine.look(NOW + timedelta(minutes=2))

    assert len(first) == 1
    assert second == third == []
    assert len(machine.alerts(NOW + timedelta(minutes=2))) == 1
    assert len(machine.logged("alpha")) == 1


def test_a_daily_alert_ends_with_its_day_and_the_next_day_is_a_new_crossing(machine):
    machine.append("acts.jsonl", door(NOW - timedelta(hours=1)), project="alpha")
    assert len(machine.look()) == 1

    tomorrow = NOW + timedelta(days=1)
    assert machine.look(tomorrow) == []
    assert machine.alerts(tomorrow) == []

    machine.append("acts.jsonl", door(tomorrow - timedelta(minutes=1)), project="alpha")
    said = machine.look(tomorrow)
    assert said == [
        "alpha: alert: kpi doors alpha: 1 one-way door opened on 2026-11-03 without the user's "
        "word, and the threshold alerts on 1"
    ]
    assert len(machine.logged("alpha")) == 2


def test_pass_time_that_recovers_ends_its_alert_and_a_new_crossing_alerts_again(machine):
    hour = NOW - timedelta(hours=2)
    passes(machine, lambda at: 61.0 if at > NOW - timedelta(hours=1) else 10.0, hour)
    assert len(machine.look()) == 1

    later = NOW + timedelta(minutes=70)
    machine.append(
        "passes.jsonl",
        *({"at": iso(NOW + timedelta(minutes=m)), "seconds": 10.0} for m in range(1, 71)),
    )
    said = machine.look(later)
    assert said == ["recovered: kpi pass-time: jbus's pass p90 10 s over the last hour"]
    assert machine.alerts(later) == []

    again = later + timedelta(minutes=70)
    machine.append(
        "passes.jsonl",
        *({"at": iso(later + timedelta(minutes=m)), "seconds": 70.0} for m in range(1, 71)),
    )
    assert len(machine.look(again)) == 1
    assert len(machine.logged("alpha")) == 2


def test_with_no_store_and_no_t3_store_nothing_is_read_and_nothing_alerts(machine):
    said: list[str] = []
    kpis.look(jbus.load(), NOW, said.append)
    assert said == []
    assert machine.alerts() == []


def test_the_stores_doc_lists_each_kpi_alert_the_code_has_and_no_other():
    doc = Path(__file__).resolve().parents[3] / "features/jbus/docs/jbus/the-telemetry-store.md"
    section = doc.read_text().split("\n## The KPI alerts\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    assert [row.split("`")[1] for row in rows] == [t.name for t in kpis.THRESHOLDS]
