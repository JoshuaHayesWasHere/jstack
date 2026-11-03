"""`jbus telemetry` compiles every project's records into one SQLite file with KPI views.

The tests write the record files of two projects as jbus writes them, run the real command, and
read the store with `sqlite3` as any reader would. A build read on from where the last one
stopped ends as a store built from nothing ends; the daily trim of `events.jsonl` loses no event
the store has read; no table, and no byte of the file, holds a text a record carried; and the
views give the scorecard's numbers.
"""

import contextlib
import importlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
import test_jbus_telemetry_tokens as token_records
from jbus import cli, telemetry, wake
from jgauge import spend as jgauge_spend

SECRET = "the user said this and it stays out"
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
TABLES = (
    "events",
    "acts",
    "items",
    "transitions",
    "outbox",
    "ci_jobs",
    "merges",
    "questions",
    "queue",
    "merged",
    "ci_prs",
    "messages",
)


def iso(moment):
    return moment.isoformat(timespec="seconds")


class T3:
    """T3 Code's store as jbus reads it: its threads, each in a project, and their messages,
    under `T3CODE_HOME`, with the time in T3 Code's own form."""

    def __init__(self):
        self.path = Path(os.environ["T3CODE_HOME"]) / "userdata" / "statev2.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            "create table orchestration_v2_projection_threads ("
            "thread_id text primary key, project_id text, payload_json text);"
            "create table orchestration_v2_projection_messages (message_id text primary key, "
            "thread_id text not null, role text not null, created_at text not null, "
            "payload_json text not null);"
        )

    def run(self, sql, *rows):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            if rows:
                db.executemany(sql, rows)
            else:
                db.executescript(sql)
            db.commit()

    def thread(self, thread, project_id):
        self.run(
            "insert into orchestration_v2_projection_threads values (?, ?, '{}')",
            (thread, project_id),
        )

    def say(self, message, thread, at, text=SECRET, role="user", by="user"):
        payload = {
            "text": text,
            "createdBy": by if role == "user" else None,
            "creationSource": "web",
        }
        self.run(
            "insert into orchestration_v2_projection_messages values (?, ?, ?, ?, ?)",
            (message, thread, role, at.strftime("%Y-%m-%dT%H:%M:%S.000Z"), json.dumps(payload)),
        )


def act_citing(machine, project, thread, message, at, verb="go", subject="alpha-one", gate=None):
    machine.append(
        project,
        "acts.jsonl",
        {
            "action": {"doors": [], "subject": subject, "verb": verb},
            "at": iso(at),
            "evidence": {"ref": f"{thread}/{message}", "source": "t3-message", "words": SECRET},
            "gate": gate,
            "id": f"act-{message}",
            "party": {"kind": "user"},
        },
    )


def word(
    machine, project, name, said, source="bot-chat", ref="winifred-chef/voice:call-1", text=SECRET
):
    """A word as `jbus word` keeps it: an act whose verb is `word`, said at `said`."""
    machine.append(
        project,
        "acts.jsonl",
        {
            "action": {"doors": [], "subject": "", "verb": "word"},
            "at": iso(said + timedelta(seconds=30)),
            "evidence": {
                "checked": False,
                "ref": ref,
                "said_at": iso(said),
                "said_in": f"{source} {ref}",
                "source": source,
                "words": text,
            },
            "gate": None,
            "id": name,
            "line": "kept",
            "outcome": "done",
            "party": {"kind": "home", "name": "", "route": "cli"},
        },
    )


def act_on_word(machine, project, name, at, verb="go", subject="alpha-one", gate=None):
    """An act that cites a word by its id, as a go given on the user's word does."""
    machine.append(
        project,
        "acts.jsonl",
        {
            "action": {"doors": [], "subject": subject, "verb": verb},
            "at": iso(at),
            "evidence": {"ref": name, "source": "typed", "words": ""},
            "gate": gate,
            "id": f"act-{name}",
            "party": {"kind": "home"},
        },
    )


class Machine:
    """A jbus config of two projects, `alpha` and `beta`, with their state and their homes."""

    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path
        config, self.state_dir, self.home_dir = (tmp_path / name for name in ("c", "s", "h"))
        lines = ['server = "http://127.0.0.1:1"']
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
        monkeypatch.setenv("JBUS_CONFIG_DIR", str(config))
        monkeypatch.setenv("JBUS_STATE_DIR", str(self.state_dir))
        monkeypatch.setenv("JBUS_HOME_DIR", str(self.home_dir))

    def state(self, project):
        return self.state_dir / project

    def append(self, project, name, *lines, home=False):
        """Add lines to a log as its writer does: each a JSON object, or text for `merge.log`."""
        path = (self.home_dir if home else self.state_dir) / project / name
        with open(path, "a") as handle:
            for line in lines:
                handle.write((line if isinstance(line, str) else json.dumps(line)) + "\n")

    def write(self, project, name, value):
        (self.state(project) / name).write_text(json.dumps(value))

    def run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["telemetry", *argv])
        return code, out.getvalue()

    def build(self):
        code, out = self.run()
        assert code == 0, out
        return out

    def store(self, path=None):
        return sqlite3.connect(path or self.state_dir / telemetry.FILE)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def event(at, slug, kind="queue", text=SECRET):
    return {
        "at": iso(at),
        "event": kind,
        "slug": slug,
        "loud": "quiet",
        "line": f"{kind} {slug}: {text}",
        "text": text,
    }


def records(machine, project, at, slug, number):
    """Write one record of each kind for a row, every text in it the user's words."""
    machine.append(project, "events.jsonl", event(at, slug))
    machine.append(
        project,
        "acts.jsonl",
        {
            "action": {"doors": [], "subject": slug, "verb": "go"},
            "at": iso(at),
            "evidence": {
                "words": SECRET,
                "said_at": "2026-10-28 11:00 ET",
                "source": "typed",
                "ref": f"thread/{slug}",
                "picks": [],
                "said_in": "",
            },
            "id": f"act-{slug}",
            "line": f"go {slug}: {SECRET}",
            "outcome": "done",
            "party": {"kind": "home", "name": "", "route": "cli"},
        },
    )
    machine.append(
        project,
        "items.jsonl",
        {
            "at": iso(at),
            "by": "jbus",
            "id": f"w{number}.1",
            "item": f"w{number}",
            "verb": "proposed",
            "slug": slug,
            "title": SECRET,
            "line": SECRET,
            "where": "pass",
        },
        {
            "at": iso(at + timedelta(minutes=1)),
            "by": "jbus",
            "id": f"w{number}.2",
            "item": f"w{number}",
            "verb": "approved",
            "line": SECRET,
            "where": "pass",
        },
    )
    machine.append(
        project,
        "transitions.jsonl",
        {"slug": slug, "from": "queued", "to": "launched", "at": iso(at + timedelta(minutes=2))},
        {
            "slug": slug,
            "from": "pr",
            "to": "merged",
            "at": iso(at + timedelta(minutes=50)),
            "why": SECRET,
        },
    )
    machine.append(
        project,
        "outbox.jsonl",
        {
            "at": iso(at),
            "thread": f"mcp:{slug}",
            "row": slug,
            "template": "drops",
            "needs": "act",
            "key": f"drops|{slug}",
            "went": "sent",
            "rule": "",
        },
    )
    machine.append(
        project,
        "merge.log",
        f"{at:%Y-%m-%d %H:%M} wait {number} https://example.test/pull/{number}: {SECRET} [no-run]",
        f"{at:%Y-%m-%d %H:%M} merged {number} {slug} {'a' * 40}",
        home=True,
    )


def snapshots(machine, project, rows):
    """Write the four snapshots for rows of (slug, number, merged time)."""
    machine.write(
        project,
        "queue.json",
        [
            {
                "slug": slug,
                "status": "merged",
                "pr": f"https://example.test/pull/{number}",
                "why": SECRET,
                "approval": {
                    "basis": "word",
                    "words": SECRET,
                    "meaning": [[SECRET]],
                    "ran_at": "2026-10-28 10:00 ET",
                },
            }
            for slug, number, _ in rows
        ],
    )
    machine.write(
        project,
        "merged.json",
        {
            slug: {
                "number": number,
                "mergedAt": iso(merged),
                "title": SECRET,
                "mergeCommit": {"oid": "b" * 40},
                "state": "MERGED",
            }
            for slug, number, merged in rows
        },
    )
    machine.write(
        project,
        "questions.json",
        {
            "next": 3,
            "records": [
                {
                    "number": 1,
                    "slug": rows[0][0],
                    "asked_at": iso(NOW),
                    "question": SECRET,
                    "default": SECRET,
                    "context": SECRET,
                    "options": [{"name": SECRET}],
                    "answer": {
                        "at": iso(NOW),
                        "by": "jbus",
                        "closed_by": "silence",
                        "words": SECRET,
                    },
                },
            ],
        },
    )
    (machine.state(project) / "ci-prs.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "number": number,
                    "branch": slug,
                    "created": iso(merged),
                    "merged": iso(merged),
                    "pushes": [],
                }
            )
            + "\n"
            for slug, number, merged in rows
        )
    )


def job(run, sha, pr, conclusion, created, attempt=1, name="check"):
    return {
        "run": run,
        "job": run * 10 + attempt,
        "attempt": attempt,
        "name": name,
        "sha": sha,
        "branch": "main",
        "pr": pr,
        "event": "push",
        "created": iso(created),
        "completed": iso(created + timedelta(minutes=5)),
        "conclusion": conclusion,
        "tests": [SECRET],
        "signs": [],
    }


def dump(path):
    """Every row of every table, in one order, without the store's own bookkeeping."""
    with contextlib.closing(sqlite3.connect(path)) as store:
        return {
            table: sorted(store.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
            for table in TABLES
        }


def test_a_build_read_on_from_the_last_one_equals_a_store_built_from_nothing(machine):
    for place, project in enumerate(("alpha", "beta")):
        records(machine, project, NOW, f"{project}-one", 10 + place)
        snapshots(machine, project, [(f"{project}-one", 10 + place, NOW + timedelta(hours=1))])
    machine.append("alpha", "ci.jsonl", job(1, "c1", 10, "success", NOW))
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    t3.say("m-1", "mcp:home-a", NOW)
    t3.say("r-1", "mcp:home-a", NOW + timedelta(seconds=20), role="assistant")
    first = machine.build()
    assert "events 2" in first and "messages 2" in first

    assert "nothing new" in machine.build()

    later = NOW + timedelta(hours=2)
    records(machine, "alpha", later, "alpha-two", 12)
    same = {
        "at": iso(later),
        "thread": "mcp:x",
        "row": "r",
        "template": "t",
        "needs": "act",
        "key": "k",
        "went": "sent",
        "rule": "",
    }
    machine.append("alpha", "outbox.jsonl", same, same)
    with open(machine.state("alpha") / "events.jsonl", "a") as handle:
        handle.write(json.dumps(event(later, "half"))[:30])
    snapshots(
        machine,
        "alpha",
        [("alpha-one", 10, NOW + timedelta(hours=1)), ("alpha-two", 12, later)],
    )
    machine.build()
    with open(machine.state("alpha") / "events.jsonl", "a") as handle:
        handle.write(json.dumps(event(later, "half"))[30:] + "\n")
    machine.append("alpha", "outbox.jsonl", same)
    machine.append("alpha", "ci.jsonl", job(2, "c2", 12, "failure", later))
    t3.say("m-2", "mcp:home-a", later)
    machine.build()

    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    built, again = dump(machine.state_dir / telemetry.FILE), dump(machine.root / "again.sqlite")
    assert built == again
    with contextlib.closing(machine.store()) as store:
        counts = dict(store.execute("SELECT project, count(*) FROM outbox GROUP BY project"))
        events = store.execute("SELECT slug FROM events WHERE project = 'alpha' ORDER BY at")
        assert counts == {"alpha": 5, "beta": 1}
        assert [one for (one,) in events] == ["alpha-one", "alpha-two", "half"]
        assert store.execute("SELECT count(*) FROM queue").fetchone() == (3,)
        assert store.execute("SELECT id FROM messages ORDER BY at").fetchall() == [
            ("m-1",),
            ("r-1",),
            ("m-2",),
        ]


def test_a_rebuild_never_writes_over_a_file(machine):
    there = machine.root / "there.sqlite"
    there.write_text("kept")
    code, out = machine.run("--rebuild", str(there))
    assert (code, out.strip()) == (2, f"refused: {there} is there, and a rebuild writes a new file")
    assert there.read_text() == "kept"


def test_the_daily_trim_drops_only_events_the_store_holds_and_the_store_keeps_them(machine):
    config = jbus.load()
    alpha = config.project("alpha")
    old, new = NOW - timedelta(days=20), NOW - timedelta(days=1)
    machine.append("alpha", "events.jsonl", event(old, "old"), event(old, "old"), event(new, "new"))
    machine.build()
    late = event(old, "late")
    machine.append("alpha", "events.jsonl", late)
    box = wake.Box(machine.state("alpha"), alpha)

    box.forget(NOW - wake.LOG_KEEP, telemetry.copied(config, alpha))

    left = (machine.state("alpha") / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["slug"] for line in left] == ["new", "late"]
    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT slug FROM events ORDER BY slug").fetchall()
        assert held == [("new",), ("old",), ("old",)]

    machine.build()
    box.forget(NOW - wake.LOG_KEEP, telemetry.copied(config, alpha))

    left = (machine.state("alpha") / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["slug"] for line in left] == ["new"]
    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT slug FROM events ORDER BY slug").fetchall()
        assert held == [("late",), ("new",), ("old",), ("old",)]


def test_with_no_store_the_trim_keeps_every_event(machine):
    config = jbus.load()
    alpha = config.project("alpha")
    machine.append("alpha", "events.jsonl", event(NOW - timedelta(days=20), "old"))
    wake.Box(machine.state("alpha"), alpha).forget(NOW, telemetry.copied(config, alpha))
    assert "old" in (machine.state("alpha") / "events.jsonl").read_text()


def test_no_table_and_no_byte_of_the_file_holds_the_text_of_a_message(machine):
    for place, project in enumerate(("alpha", "beta")):
        records(machine, project, NOW, f"{project}-one", 10 + place)
        snapshots(machine, project, [(f"{project}-one", 10 + place, NOW + timedelta(hours=1))])
    machine.append("alpha", "ci.jsonl", job(1, "c1", 10, "failure", NOW))
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    t3.say("m-1", "mcp:home-a", NOW)
    t3.say("r-1", "mcp:home-a", NOW + timedelta(seconds=20), text=SECRET, role="assistant")
    word(machine, "beta", "w-1", NOW)
    machine.build()

    found = dump(machine.state_dir / telemetry.FILE)
    assert all(found[table] for table in TABLES)
    cells = [cell for rows in found.values() for row in rows for cell in row]
    assert not [cell for cell in cells if isinstance(cell, str) and "said this" in cell]
    files = sorted(machine.state_dir.glob(f"{telemetry.FILE}*"))
    assert files
    for path in files:
        assert SECRET.encode() not in path.read_bytes()
    assert stat.S_IMODE((machine.state_dir / telemetry.FILE).stat().st_mode) == 0o600
    with contextlib.closing(machine.store()) as store:
        lengths = store.execute("SELECT words_len FROM acts").fetchall()
        assert lengths == [(len(SECRET),)] * 3


def scorecard_pct(values, share):
    """`pct` of `reports/week-audit/scorecard.py`."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


@pytest.mark.parametrize("n", range(1, 11))
def test_a_weeks_lead_time_is_the_scorecards_median_and_85th(machine, n):
    minutes = [7 * (place * 37 % 11) + place for place in range(n)]
    machine.write(
        "alpha",
        "queue.json",
        [{"slug": f"row-{place}", "approval": {"ran_at": iso(NOW)}} for place in range(n)],
    )
    machine.write(
        "alpha",
        "merged.json",
        {
            f"row-{place}": {"number": place, "mergedAt": iso(NOW + timedelta(minutes=value))}
            for place, value in enumerate(minutes)
        },
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        week, count, median, p85 = store.execute(
            "SELECT week, n, median, p85 FROM weekly_lead_time"
        ).fetchone()
    assert (week, count) == ("2026-10-25", n)
    assert median == pytest.approx(statistics.median(minutes))
    assert p85 == pytest.approx(scorecard_pct(minutes, 0.85))


def test_a_rows_go_is_its_earliest_of_approval_go_and_launch_and_its_day_is_the_users(machine):
    late = datetime(2026, 11, 1, 2, 30, tzinfo=UTC)
    machine.append(
        "alpha",
        "items.jsonl",
        {
            "at": iso(late - timedelta(hours=3)),
            "id": "w1.1",
            "item": "w1",
            "verb": "proposed",
            "slug": "row",
        },
        {"at": iso(late - timedelta(hours=2)), "id": "w1.2", "item": "w1", "verb": "approved"},
    )
    machine.append(
        "alpha",
        "transitions.jsonl",
        {"slug": "row", "from": "queued", "to": "launched", "at": iso(late - timedelta(hours=1))},
        {"slug": "row", "from": "pr", "to": "merged", "at": iso(late)},
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        row = store.execute("SELECT minutes, day, week FROM lead_times").fetchone()
    assert row == (120.0, "2026-10-31", "2026-10-25")


def test_spells_restore_and_change_failure_follow_the_push_checks_on_main(machine):
    at = NOW
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, "c1", 1, "success", at),
        job(2, "c2", 2, "failure", at + timedelta(minutes=10)),
        job(3, "c3", 3, "failure", at + timedelta(minutes=20)),
        job(4, "c4", 4, "failure", at + timedelta(minutes=30)),
        job(4, "c4", 4, "success", at + timedelta(minutes=40), attempt=2),
        job(5, "c5", 5, "failure", at + timedelta(minutes=50)),
        job(5, "c5", 5, "cancelled", at + timedelta(minutes=50), name="full"),
    )
    merged = {
        f"row-{n}": {"number": n, "mergedAt": iso(at + timedelta(minutes=10 * n - 11))}
        for n in range(1, 6)
    }
    machine.write("alpha", "merged.json", merged)
    machine.write("alpha", "queue.json", [{"slug": slug} for slug in merged])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        spells = store.execute(
            "SELECT start_pr, end_sha, minutes_to_green FROM main_spells ORDER BY first_fail_at"
        ).fetchall()
        restore = store.execute(
            "SELECT week, spells, median, most, still_open FROM weekly_restore"
        ).fetchall()
        failure = store.execute(
            "SELECT week, failures, merged FROM weekly_change_failure"
        ).fetchall()
    assert spells == [(2, "c4", 30.0), (5, None, None)]
    assert restore == [("2026-10-25", 2, 30.0, 30.0, 1)]
    assert failure == [("2026-10-25", 2, 5)]


def merged_rows(machine, project, rows):
    """Merged rows of (slug, number, merged time), each with its pull request in `ci-prs.jsonl`."""
    snapshots(machine, project, rows)
    machine.write(project, "queue.json", [{"slug": slug} for slug, _, _ in rows])


def test_the_change_failure_rate_counts_only_projects_whose_push_checks_the_store_holds(machine):
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, "c1", 1, "failure", NOW),
        job(2, "c2", 2, "success", NOW + timedelta(minutes=10)),
    )
    merged_rows(machine, "alpha", [("a-1", 1, NOW), ("a-2", 2, NOW + timedelta(minutes=9))])
    merged_rows(machine, "beta", [("b-1", 3, NOW), ("b-2", 4, NOW + timedelta(minutes=9))])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        failure = store.execute(
            "SELECT week, failures, merged FROM weekly_change_failure"
        ).fetchall()
        assert failure == [("2026-10-25", 1, 2)]
        assert store.execute("SELECT project FROM ci_projects").fetchall() == [("alpha",)]


def test_a_merged_row_with_no_push_check_kept_is_a_gap_the_rate_leaves_out(machine):
    gap = NOW - timedelta(days=2)
    machine.append("alpha", "ci.jsonl", job(1, "c1", 1, "success", NOW))
    merged_rows(machine, "alpha", [("a-1", 1, NOW), ("a-0", 9, gap)])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        failure = store.execute(
            "SELECT week, failures, merged FROM weekly_change_failure"
        ).fetchall()
        assert failure == [("2026-10-25", 0, 1)]
        gaps = store.execute("SELECT project, day, week FROM ci_gaps").fetchall()
        assert gaps == [("alpha", "2026-10-26", "2026-10-25")]


def test_a_prs_merge_day_is_its_own_merge_line_not_an_older_repos_of_the_same_number(machine):
    opened = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
    machine.append(
        "alpha",
        "merge.log",
        f"2026-10-12 12:00 merged 7 old-row {'a' * 40}",
        f"2026-10-28 12:00 merged 7 new-row {'b' * 40}",
        home=True,
    )
    (machine.state("alpha") / "ci-prs.jsonl").write_text(
        json.dumps(
            {
                "number": 7,
                "branch": "new-row",
                "created": iso(opened),
                "merged": iso(opened + timedelta(days=1, hours=1)),
                "pushes": [],
            }
        )
        + "\n"
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        times = store.execute("SELECT pr, day, week, minutes FROM pr_times").fetchall()
    assert times == [(7, "2026-10-28", "2026-10-25", 1500.0)]


def test_a_pass_builds_the_store_with_what_its_project_logged_before_it(kitchen):
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.record("note", "a note", SECRET)
    logged = (kitchen.state / "events.jsonl").read_text().splitlines()
    kitchen.poll()
    with contextlib.closing(sqlite3.connect(kitchen.state_dir / telemetry.FILE)) as store:
        held = store.execute("SELECT count(*) FROM events WHERE project = 'demo'").fetchone()[0]
    assert logged and held >= len(logged)
    assert SECRET.encode() not in (kitchen.state_dir / telemetry.FILE).read_bytes()


def counted(path, version):
    """A store as a jbus that counted its migrations by `PRAGMA user_version` left it, at this
    version."""
    from jbus.telemetry import migrations

    with contextlib.closing(sqlite3.connect(path)) as store:
        for number, sql in enumerate(list(migrations.MIGRATIONS.values())[:version], 1):
            store.executescript(f"BEGIN;\n{sql}PRAGMA user_version = {number};\nCOMMIT;")


def test_a_store_made_at_version_1_migrates_to_every_column_each_table_names(machine):
    from jbus.telemetry import messages, migrations
    from jbus.telemetry import records as kept

    old, new = machine.root / "old.sqlite", machine.root / "new.sqlite"
    counted(old, 1)
    for path in (old, new):
        telemetry.connect(path).close()
        with contextlib.closing(sqlite3.connect(path)) as store:
            assert telemetry.ran(store) == set(migrations.MIGRATIONS)
            tables = [(source.table, source.columns) for source in kept.SOURCES]
            for table, named in [*tables, (messages.TABLE, messages.COLUMNS)]:
                columns = {row[1] for row in store.execute(f"PRAGMA table_info({table})")}
                assert {name for name, _ in named} <= columns, table


def schema_of(path):
    with contextlib.closing(sqlite3.connect(path)) as store:
        version = store.execute("PRAGMA user_version").fetchone()[0]
        found = store.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name")
        return version, telemetry.ran(store), found.fetchall()


def test_a_store_at_each_earlier_version_migrates_to_the_schema_a_new_store_has(machine):
    from jbus.telemetry import migrations

    new = machine.root / "new.sqlite"
    telemetry.connect(new).close()
    assert schema_of(new)[:2] == (0, set(migrations.MIGRATIONS))
    for version in range(len(migrations.MIGRATIONS) + 1):
        old = machine.root / f"at-{version}.sqlite"
        counted(old, version)
        telemetry.connect(old).close()
        assert schema_of(old) == schema_of(new), version


@pytest.mark.parametrize("version", [0, 7, 9])
def test_a_store_counted_by_version_keeps_the_names_of_its_migrations_once(machine, version):
    """A store at `user_version` n is moved to the table once with the first n names, and runs
    only the migrations after them: a migration it had run again would fail its CREATE."""
    from jbus.telemetry import migrations

    names = list(migrations.MIGRATIONS)
    path = machine.root / f"at-{version}.sqlite"
    counted(path, version)
    with contextlib.closing(sqlite3.connect(path)) as store:
        if version:
            store.executescript("INSERT INTO meta (name, value) VALUES ('kept', 'yes');")
        tables_before = {name for (name,) in store.execute("SELECT name FROM sqlite_master")}

    with contextlib.closing(sqlite3.connect(path, isolation_level=None)) as store:
        telemetry.migrate(store)
        moved = sorted(name for (name,) in store.execute("SELECT name FROM migrations"))
        telemetry.migrate(store)
        again = sorted(name for (name,) in store.execute("SELECT name FROM migrations"))
        version_after = store.execute("PRAGMA user_version").fetchone()[0]
        tables = {name for (name,) in store.execute("SELECT name FROM sqlite_master")}
        held = store.execute("SELECT value FROM meta WHERE name = 'kept'").fetchall()

    assert moved == again == names
    assert version_after == 0
    assert tables >= tables_before | {"migrations", "cursors", "acts", "gate_labels", "drift"}
    if version:
        assert names[version - 1] == {7: "v007_asks", 9: "v009_drift"}[version]
        assert held == [("yes",)]
    else:
        assert tables_before == set()


def migrations_with(tmp_path, monkeypatch, name, files):
    """A copy of the migrations' package named `name`, with these modules added, imported."""
    from jbus.telemetry import migrations

    root = tmp_path / "packages"
    shutil.copytree(
        migrations.__path__[0], root / name, ignore=shutil.ignore_patterns("__pycache__")
    )
    for file, text in files.items():
        (root / name / file).write_text(text)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    return importlib.import_module(name)


def test_a_migration_is_added_by_a_module_after_the_last_one(tmp_path, monkeypatch):
    from jbus.telemetry import migrations

    added = 'SQL = "CREATE TABLE added (x TEXT);\\n"\n'
    file = f"v{len(migrations.MIGRATIONS) + 1:03d}_added.py"
    found = migrations_with(tmp_path, monkeypatch, "added_migrations", {file: added})

    assert found.MIGRATIONS == {
        **migrations.MIGRATIONS,
        file[:-3]: "CREATE TABLE added (x TEXT);\n",
    }


def test_two_migrations_of_one_number_both_run_once_whichever_a_store_had(
    machine, tmp_path, monkeypatch
):
    """Two changes that each add a migration of the same number, and a gap before them, both
    run: on a store that had neither, and on one that had the first to merge."""
    from jbus.telemetry import migrations

    last = len(migrations.MIGRATIONS)
    files = {
        f"v{last + 3:03d}_{side}.py": f'SQL = "CREATE TABLE {side} (x TEXT);\\n"\n'
        for side in ("left", "right")
    }
    found = migrations_with(tmp_path, monkeypatch, "twin_migrations", files)
    assert list(found.MIGRATIONS)[last:] == [f"v{last + 3:03d}_left", f"v{last + 3:03d}_right"]
    monkeypatch.setattr(telemetry, "migrations", found)

    neither, right = machine.root / "neither.sqlite", machine.root / "right.sqlite"
    counted(right, last)
    with contextlib.closing(sqlite3.connect(right, isolation_level=None)) as store:
        telemetry.migrate(store)
        store.execute(f"DELETE FROM migrations WHERE name = 'v{last + 3:03d}_left'")
        store.execute("DROP TABLE left")
    for path in (neither, right):
        telemetry.connect(path).close()
        telemetry.connect(path).close()
        with contextlib.closing(sqlite3.connect(path)) as store:
            assert telemetry.ran(store) == set(found.MIGRATIONS), path
            for table in ("left", "right"):
                assert store.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_a_migration_not_named_with_three_digits_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ImportError):
        migrations_with(tmp_path, monkeypatch, "refused_migrations", {"v12_short.py": 'SQL = ""\n'})


def test_a_pass_logs_its_seconds_and_the_next_build_keeps_them_as_the_machines(kitchen):
    kitchen.poll()
    lines = (kitchen.state_dir / "passes.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert isinstance(json.loads(lines[0])["seconds"], float)
    kitchen.poll()
    with contextlib.closing(sqlite3.connect(kitchen.state_dir / telemetry.FILE)) as store:
        held = store.execute("SELECT project, seconds IS NOT NULL FROM passes").fetchall()
    assert held == [("", 1)]


def test_each_typed_message_joins_a_row_an_answer_or_a_reply_or_is_a_lost_ask(machine):
    """S3 with no labels: a message the user typed joins the act that cites it, a row first,
    then an answer, else the assistant's first reply in its thread within the wait; with none,
    it waits, then is lost. Only what the user typed is counted."""
    t3, home, crew = T3(), "mcp:home-a", "mcp:crew-a"
    t3.thread(home, "alpha-id")
    t3.thread(crew, "alpha-id")
    t3.thread("mcp:scratch", "scratch-id")
    wait = timedelta(minutes=telemetry.schema.WAIT)
    t3.say("m-row", home, NOW)
    act_citing(machine, "alpha", home, "m-row", NOW + 3 * wait)
    t3.say("m-answer", home, NOW + timedelta(minutes=1))
    act_citing(machine, "beta", home, "m-answer", NOW + timedelta(minutes=2), "answer", gate=4)
    t3.say("m-reply", home, NOW + timedelta(minutes=10), text="/crew some-row")
    t3.say("r-reply", home, NOW + timedelta(minutes=10, seconds=30), role="assistant")
    t3.say("m-late", crew, NOW + timedelta(hours=1))
    t3.say("r-late", crew, NOW + timedelta(hours=1) + wait + timedelta(minutes=1), role="assistant")
    t3.say("m-none", home, NOW + 2 * wait)
    t3.say("r-elsewhere", crew, NOW + 2 * wait + timedelta(minutes=1), role="assistant")
    t3.say("m-scratch", "mcp:scratch", NOW, text="continue where you left off.")
    t3.say("r-scratch", "mcp:scratch", NOW + timedelta(seconds=5), role="assistant")
    t3.say("m-agent", home, NOW, by="agent")
    t3.say("m-reminder", home, NOW, text="<system-reminder>a hook said this</system-reminder>")
    t3.say("limit-resume:1", home, NOW)
    t3.say("m-waiting", home, datetime.now(UTC) - timedelta(minutes=5))
    machine.build()

    with contextlib.closing(machine.store()) as store:
        ledger = store.execute(
            "SELECT project, id, kind, joined, link FROM ask_ledger ORDER BY id"
        ).fetchall()
        weeks = store.execute(
            "SELECT week, typed, lost, waiting FROM weekly_lost_asks ORDER BY week"
        ).fetchall()
    assert ledger == [
        ("alpha", "m-answer", "text", "answer", "act-m-answer"),
        ("alpha", "m-late", "text", "unanswered", None),
        ("alpha", "m-none", "text", "unanswered", None),
        ("alpha", "m-reply", "command", "reply", "r-reply"),
        ("alpha", "m-row", "text", "row", "act-m-row"),
        ("scratch-id", "m-scratch", "resume", "reply", "r-scratch"),
        ("alpha", "m-waiting", "text", "waiting", None),
    ]
    assert weeks[0] == ("2026-10-25", 6, 2, 0)
    assert weeks[-1][1:] == (0, 0, 1)


def test_a_word_said_in_the_bots_chat_is_a_typed_message_and_joins_like_one(machine):
    """A word the user said through the bots' chat is one row of `messages` with no text, in
    the thread jbus carried it to, and joins the act that cites it by its id, a row first, then
    an answer, else the first reply in that thread within the wait; with none, it is lost."""
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    wait = timedelta(minutes=telemetry.schema.WAIT)
    word(machine, "alpha", "w-row", NOW)
    act_on_word(machine, "alpha", "w-row", NOW + 3 * wait)
    word(machine, "beta", "w-answer", NOW + timedelta(minutes=1), source="view", ref="")
    act_on_word(machine, "beta", "w-answer", NOW + timedelta(minutes=2), "answer", gate=4)
    word(machine, "alpha", "w-reply", NOW + timedelta(minutes=10))
    t3.say("r-reply", home, NOW + timedelta(minutes=11), role="assistant")
    word(machine, "alpha", "w-lost", NOW + timedelta(hours=1))
    t3.say("r-lost", home, NOW + timedelta(hours=1) + wait + timedelta(minutes=1), role="assistant")
    word(machine, "alpha", "w-waiting", datetime.now(UTC) - timedelta(minutes=5))
    sent = {"sent_at": iso(NOW), "thread": home, "waits": ""}
    machine.write("alpha", "word-sends.json", {"w-reply": sent, "w-lost": sent})
    machine.build()
    assert "nothing new" in machine.build()

    with contextlib.closing(machine.store()) as store:
        rows = store.execute(
            "SELECT project, key, thread, role, created_by, creation_source, kind, text_len "
            "FROM messages WHERE role = 'user' ORDER BY key"
        ).fetchall()
        ledger = store.execute(
            "SELECT project, id, kind, joined, link FROM ask_ledger ORDER BY at"
        ).fetchall()
        weeks = store.execute("SELECT week, typed, lost, waiting FROM weekly_lost_asks").fetchall()
    assert rows == [
        ("beta", "word:w-answer", None, "user", "user", "word:view", "text", len(SECRET)),
        ("alpha", "word:w-lost", home, "user", "user", "word:bot-chat", "text", len(SECRET)),
        ("alpha", "word:w-reply", home, "user", "user", "word:bot-chat", "text", len(SECRET)),
        ("alpha", "word:w-row", None, "user", "user", "word:bot-chat", "text", len(SECRET)),
        ("alpha", "word:w-waiting", None, "user", "user", "word:bot-chat", "text", len(SECRET)),
    ]
    assert ledger == [
        ("alpha", "w-row", "text", "row", "act-w-row"),
        ("beta", "w-answer", "text", "answer", "act-w-answer"),
        ("alpha", "w-reply", "text", "reply", "r-reply"),
        ("alpha", "w-lost", "text", "unanswered", None),
        ("alpha", "w-waiting", "text", "waiting", None),
    ]
    assert weeks[0] == ("2026-10-25", 4, 1, 0)


ASKS = "Does anything need me? Is everything moving?"
"""A message that asks what needs the user, as the user typed one on 2026-10-30."""
TELLS = "rename archlinux to Yelena, and ship it"


def test_a_typed_message_keeps_whether_it_asks_what_needs_the_user_and_no_word_of_it(machine):
    """Each message the user typed, and each word said through the bots' chat, keeps one label
    as it is read: `needs` where it asks what needs the user, `other` where it does not. An
    assistant's message has none, and no table or byte of the store holds the text."""
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    t3.say("m-asks", home, NOW, text=ASKS)
    t3.say("m-tells", home, NOW + timedelta(minutes=1), text=TELLS)
    t3.say("m-why", home, NOW + timedelta(minutes=2), text="why do these need me?")
    t3.say("m-quoted", home, NOW + timedelta(minutes=3), text='cut the "what needs me" asks')
    t3.say("m-command", home, NOW + timedelta(minutes=4), text="/crew what needs me")
    t3.say("r-asks", home, NOW + timedelta(minutes=5), text=ASKS, role="assistant")
    word(machine, "alpha", "w-asks", NOW + timedelta(minutes=6), text="anything else need me?")
    word(machine, "alpha", "w-tells", NOW + timedelta(minutes=7), text=TELLS)
    machine.build()

    with contextlib.closing(machine.store()) as store:
        labels = store.execute("SELECT key, kind, asks FROM messages ORDER BY at").fetchall()
        ledger = store.execute("SELECT id, asks FROM ask_ledger ORDER BY at").fetchall()
    assert labels == [
        ("m-asks", "text", "needs"),
        ("m-tells", "text", "other"),
        ("m-why", "text", "other"),
        ("m-quoted", "text", "other"),
        ("m-command", "command", "other"),
        ("r-asks", None, None),
        ("word:w-asks", "text", "needs"),
        ("word:w-tells", "text", "other"),
    ]
    assert dict(ledger)["m-asks"] == "needs" and dict(ledger)["w-tells"] == "other"
    for path in machine.state_dir.glob(f"{telemetry.FILE}*"):
        held = path.read_bytes()
        assert not [text for text in (ASKS, TELLS, "need me") if text.encode() in held]


def test_a_store_built_before_the_labels_gains_them_as_a_rebuild_has_them(machine):
    """A store read before messages kept what they ask is migrated, reads every message and
    every word again, and ends with the labels a store built from nothing has."""
    from jbus.telemetry import migrations, views

    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    t3.say("m-asks", home, NOW, text=ASKS)
    t3.say("m-tells", home, NOW + timedelta(minutes=1), text=TELLS)
    word(machine, "alpha", "w-asks", NOW + timedelta(minutes=2), text="what needs me?")
    word(machine, "beta", "w-tells", NOW + timedelta(minutes=3), text=TELLS)
    records(machine, "alpha", NOW, "alpha-one", 10)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        signed = store.execute("SELECT value FROM meta WHERE name = 'messages'").fetchone()[0]
        views = "".join(f"DROP VIEW {name};" for name, _ in reversed(views.VIEWS))
        names = list(migrations.MIGRATIONS)
        rewound = names[names.index("v007_asks") :]
        later = "".join(
            f"DROP TABLE {table};"
            for name in rewound[1:]
            for table in re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", migrations.MIGRATIONS[name]
            )
        )
        unrun = "".join(f"DELETE FROM migrations WHERE name = '{name}';" for name in rewound)
        store.executescript(
            f"{views}{later}ALTER TABLE messages DROP COLUMN asks; "
            f"ALTER TABLE acts DROP COLUMN asks; {unrun}"
        )
        store.execute(
            "UPDATE meta SET value = ? WHERE name = 'messages'",
            ("1 " + signed.split(" ", 1)[1],),
        )
        store.commit()

    machine.build()

    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    built, again = dump(machine.state_dir / telemetry.FILE), dump(machine.root / "again.sqlite")
    assert built == again
    with contextlib.closing(machine.store()) as store:
        labels = store.execute("SELECT key, asks FROM messages ORDER BY at").fetchall()
        acts = store.execute("SELECT id, asks FROM acts WHERE verb = 'word' ORDER BY id").fetchall()
    assert labels == [
        ("m-asks", "needs"),
        ("m-tells", "other"),
        ("word:w-asks", "needs"),
        ("word:w-tells", "other"),
    ]
    assert acts == [("w-asks", "needs"), ("w-tells", "other")]


def test_a_word_carried_into_a_t3_thread_or_said_in_one_is_one_ask(machine):
    """The message jbus carries a word in is T3 Code's, not the user's, and a word recorded
    from the user's own T3 message is that message: each word is one ask."""
    t3, home, crew = T3(), "mcp:home-a", "mcp:crew-a"
    t3.thread(home, "alpha-id")
    t3.thread(crew, "alpha-id")
    word(machine, "alpha", "w-chat", NOW)
    machine.write(
        "alpha", "word-sends.json", {"w-chat": {"sent_at": iso(NOW), "thread": home, "waits": ""}}
    )
    carried = "message:mcp:client:thread-send:word%7Calpha%7Cw-chat%7Cmcp%3Ahome-a"
    t3.say(carried, home, NOW + timedelta(seconds=40), by="agent")
    t3.say("r-chat", home, NOW + timedelta(minutes=1), role="assistant")
    t3.say("m-typed", crew, NOW + timedelta(minutes=5))
    word(machine, "alpha", "w-typed", NOW + timedelta(minutes=5), "t3-message", f"{crew}/m-typed")
    t3.say("r-typed", crew, NOW + timedelta(minutes=6), role="assistant")
    machine.build()

    with contextlib.closing(machine.store()) as store:
        ledger = store.execute("SELECT id, joined FROM ask_ledger ORDER BY at").fetchall()
        typed = store.execute("SELECT typed FROM weekly_lost_asks").fetchall()
    assert [one for one, _ in ledger] == ["w-chat", "m-typed"]
    assert ledger[0] == ("w-chat", "reply")
    assert typed == [(2,)]


def test_a_door_the_home_opens_on_a_message_the_user_typed_is_the_users(machine):
    """A door act counts as the user's when the user did it, or when the home did it on a
    message the user typed (`--message`) or on a word the user said; on a message an agent or
    the home wrote, or on none, it is not the user's."""
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    t3.say("m-typed", home, NOW)
    t3.say("m-agent", home, NOW, by="agent")
    t3.say("r-home", home, NOW + timedelta(seconds=5), role="assistant")
    word(machine, "alpha", "w-said", NOW)

    def door(name, party, ref):
        machine.append(
            "alpha",
            "acts.jsonl",
            {
                "action": {"doors": ["merge"], "subject": "alpha-one", "verb": "go"},
                "at": iso(NOW + timedelta(minutes=1)),
                "evidence": {"ref": ref, "source": "t3-message", "words": SECRET},
                "gate": None,
                "id": name,
                "outcome": "done",
                "party": {"kind": party, "name": "", "route": "cli"},
            },
        )

    door("by-user", "user", "")
    door("on-typed", "home", f"{home}/m-typed")
    door("on-word", "home", "w-said")
    door("on-agent", "home", f"{home}/m-agent")
    door("on-reply", "home", f"{home}/r-home")
    door("on-none", "home", "")
    machine.build()

    with contextlib.closing(machine.store()) as store:
        weeks = store.execute("SELECT week, done, not_yours FROM weekly_doors").fetchall()
    assert weeks == [("2026-10-25", 6, 3)]


def test_a_t3_store_numbered_again_or_replaced_is_read_again_and_keeps_one_row_a_message(machine):
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    for n in range(3):
        t3.say(f"m-{n}", "mcp:home-a", NOW + timedelta(minutes=n))
    machine.build()
    assert "nothing new" in machine.build()

    t3.run(
        "create table kept as select message_id, thread_id, role, created_at, payload_json "
        "from orchestration_v2_projection_messages where message_id <> 'm-0';"
        "delete from orchestration_v2_projection_messages;"
        "insert into orchestration_v2_projection_messages select * from kept;"
        "drop table kept;"
    )
    t3.say("m-3", "mcp:home-a", NOW + timedelta(minutes=3))
    machine.build()

    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT project, id FROM messages ORDER BY id").fetchall()
    assert held == [("alpha", f"m-{n}") for n in range(4)]


def test_a_project_jbus_learns_later_takes_its_messages_under_its_name_one_row_a_message(machine):
    t3 = T3()
    t3.thread("mcp:scratch", "scratch-id")
    t3.say("m-1", "mcp:scratch", NOW)
    machine.build()
    config = machine.root / "c" / "config.toml"
    config.write_text(
        config.read_text()
        + f'[[project]]\nname = "gamma"\ncheckout = "{machine.root / "gamma"}"\n'
        + 'projectId = "scratch-id"\n'
    )
    (machine.state_dir / "gamma").mkdir()

    machine.build()

    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT project, id FROM messages").fetchall()
    assert held == [("gamma", "m-1")]


def test_a_t3_store_that_cannot_be_read_leaves_the_rest_of_the_build(machine):
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    t3.say("m-0", "mcp:home-a", NOW)
    machine.build()
    t3.path.write_text("not a database")
    records(machine, "alpha", NOW, "alpha-one", 10)

    out = machine.build()

    assert "events 1" in out and "messages" not in out
    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT id FROM messages").fetchall()
    assert held == [("m-0",)]


def test_a_raised_rules_reads_every_message_again_under_the_new_kind(machine, monkeypatch):
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    for n in range(3):
        t3.say(f"m-{n}", "mcp:home-a", NOW + timedelta(minutes=n))
    machine.build()
    monkeypatch.setattr(telemetry.messages, "kind", lambda message_id, head: "relabelled")
    assert "nothing new" in machine.build()

    monkeypatch.setattr(telemetry.messages, "RULES", telemetry.messages.RULES + 1)
    machine.build()

    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT id, kind FROM messages ORDER BY id").fetchall()
    assert held == [(f"m-{n}", "relabelled") for n in range(3)]


def test_the_most_cap_leaves_the_messages_past_it_for_the_next_build(machine, monkeypatch):
    monkeypatch.setattr(telemetry.messages, "BATCH", 2)
    t3 = T3()
    t3.thread("mcp:home-a", "alpha-id")
    for n in range(5):
        t3.say(f"m-{n}", "mcp:home-a", NOW + timedelta(minutes=n))

    capped = telemetry.build(jbus.load(), most=1)

    assert capped.left == 1
    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT id FROM messages ORDER BY id").fetchall()
    assert held == [("m-0",), ("m-1",)]

    machine.build()

    with contextlib.closing(machine.store()) as store:
        held = store.execute("SELECT id FROM messages ORDER BY id").fetchall()
    assert held == [(f"m-{n}",) for n in range(5)]


def spent(day, at, units, sends=0, homes=0, capped=0):
    """A day's line of `spend.jsonl`, as `jbus.spent` keeps it."""
    return {
        "day": day,
        "at": iso(at),
        "units": units,
        "runs": 1,
        "input": 0,
        "cached": 0,
        "written": 0,
        "output": 0,
        "first": units - sends - homes - capped,
        "reviews": 0,
        "fixes": 0,
        "sends": sends,
        "homes": homes,
        "scouts": 0,
        "capped": capped,
    }


def test_the_weeks_spend_gives_the_coordination_and_capped_shares_of_each_days_last_line(machine):
    """Each week of the days spent, by every project's last line of each day: jbus's sends and
    the homes over all units, and the runs that failed on a cap over all units. A week of days
    with no run has no share."""
    later = NOW + timedelta(days=2)
    machine.append(
        "alpha",
        "spend.jsonl",
        spent("2026-10-27", NOW, 1000, sends=100, homes=50, capped=10),
        spent("2026-10-27", later, 2000, sends=200, homes=100, capped=20),
        spent("2026-10-20", NOW - timedelta(days=7), 500, capped=50),
        spent("2026-10-13", NOW - timedelta(days=14), 0),
    )
    machine.append("beta", "spend.jsonl", spent("2026-10-28", later, 1000, homes=100))
    machine.build()

    with contextlib.closing(machine.store()) as store:
        weeks = store.execute(
            "SELECT week, units, coordination, capped FROM weekly_spend ORDER BY week"
        ).fetchall()
    assert weeks == [
        ("2026-10-11", 0, None, None),
        ("2026-10-18", 500, 0, 10),
        ("2026-10-25", 3000, pytest.approx(100 * 400 / 3000), pytest.approx(100 * 20 / 3000)),
    ]


def test_a_merged_row_is_finished_with_no_further_word_unless_a_typed_word_after_its_go_names_it(
    machine,
):
    """S1: a merged row is quiet unless a message the user typed after its go, and by its merge,
    is cited by an act of the row's project on the row, or was typed in the row's own thread. A
    word before the go, after the merge, or T3 Code's resume after a cap is no further word."""
    rows = [(f"alpha-{n}", n, NOW + timedelta(hours=1)) for n in ("one", "two", "three", "four")]
    for slug, _, _ in rows:
        records(machine, "alpha", NOW, slug, len(slug))
    snapshots(machine, "alpha", rows)
    queue = json.loads((machine.state("alpha") / "queue.json").read_text())
    machine.write("alpha", "queue.json", [{**row, "thread": f"mcp:{row['slug']}"} for row in queue])
    t3, home = T3(), "mcp:home-a"
    for thread in (home, *(f"mcp:{slug}" for slug, _, _ in rows)):
        t3.thread(thread, "alpha-id")
    t3.say("m-one", home, NOW)
    act_citing(machine, "alpha", home, "m-one", NOW + timedelta(minutes=1), "hold", "alpha-one")
    t3.say("m-two", "mcp:alpha-two", NOW)
    t3.say("m-go", home, NOW - timedelta(hours=2))
    act_citing(machine, "alpha", home, "m-go", NOW - timedelta(hours=2), "go", "alpha-three")
    t3.say("m-resume", "mcp:alpha-three", NOW, text="continue where you left off.")
    t3.say("m-after", "mcp:alpha-four", NOW + timedelta(hours=2))
    machine.build()

    with contextlib.closing(machine.store()) as store:
        words = store.execute("SELECT slug, words FROM row_words ORDER BY slug").fetchall()
        weeks = store.execute("SELECT week, merged, quiet, share FROM weekly_no_word").fetchall()
    assert words == [("alpha-four", 0), ("alpha-one", 1), ("alpha-three", 0), ("alpha-two", 1)]
    assert weeks == [("2026-10-25", 4, 2, 50.0)]


def test_spend_per_merged_row_is_each_weeks_row_spend_over_its_rows_that_spent(
    tmp_path, monkeypatch, t3_settings
):
    """Each merge week, the units the threads of its merged rows spent, over the rows with any
    spend recorded, in millions: a row merged with no call recorded is left out, and a home's
    spend is no row's."""
    tokens = token_records.Machine(tmp_path, monkeypatch, t3_settings)
    sonnet = "claude-sonnet-5-5"
    for session, title, plain in (
        ("s1", "crew: row-a", 1_000_000),
        ("s2", "review: row-a", 500_000),
        ("s3", "crew: row-b", 3_000_000),
        ("s4", "crew: row-d", 500_000),
        ("s9", "home: alpha", 9_000_000),
    ):
        tokens.thread(f"mcp:{session}", title, "claudeAgent", session)
        tokens.claude(
            session,
            token_records.said(NOW, f"m-{session}", (plain, 0, 0, 0), sonnet, session=session),
        )
    merged = {"row-a": NOW, "row-b": NOW - timedelta(days=7), "row-d": NOW, "row-e": NOW}
    state = tokens.state_dir / "alpha"
    (state / "queue.json").write_text(json.dumps([{"slug": slug} for slug in merged]))
    (state / "merged.json").write_text(
        json.dumps(
            {
                slug: {"number": n, "mergedAt": iso(at + timedelta(hours=1))}
                for n, (slug, at) in enumerate(merged.items(), 1)
            }
        )
    )
    tokens.run()

    with tokens.store() as store:
        weeks = store.execute(
            "SELECT week, rows, per_row FROM weekly_row_spend ORDER BY week"
        ).fetchall()
    assert weeks == [
        ("2026-10-18", 1, pytest.approx(3 * jgauge_spend.PLAIN)),
        ("2026-10-25", 2, pytest.approx(1 * jgauge_spend.PLAIN)),
    ]
