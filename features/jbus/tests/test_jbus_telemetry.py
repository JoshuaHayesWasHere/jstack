"""`jbus telemetry` compiles every project's records into one SQLite file with KPI views.

The tests write the record files of two projects as jbus writes them, run the real command, and
read the store with `sqlite3` as any reader would. A build read on from where the last one
stopped ends as a store built from nothing ends; the daily trim of `events.jsonl` loses no event
the store has read; no table, and no byte of the file, holds a text a record carried; and the
views give the scorecard's numbers.
"""

import contextlib
import io
import json
import sqlite3
import stat
import statistics
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import cli, telemetry, wake

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
)


def iso(moment):
    return moment.isoformat(timespec="seconds")


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
    first = machine.build()
    assert "events 2" in first and "nothing new" not in first

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
        assert lengths == [(len(SECRET),), (len(SECRET),)]


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


def test_a_pass_builds_the_store_with_what_its_project_logged_before_it(kitchen):
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.record("note", "a note", SECRET)
    logged = (kitchen.state / "events.jsonl").read_text().splitlines()
    kitchen.poll()
    with contextlib.closing(sqlite3.connect(kitchen.state_dir / telemetry.FILE)) as store:
        held = store.execute("SELECT count(*) FROM events WHERE project = 'demo'").fetchone()[0]
    assert logged and held >= len(logged)
    assert SECRET.encode() not in (kitchen.state_dir / telemetry.FILE).read_bytes()


def test_a_store_made_at_version_1_migrates_to_every_column_each_source_names(machine):
    from jbus.telemetry import records as kept
    from jbus.telemetry import schema

    old, new = machine.root / "old.sqlite", machine.root / "new.sqlite"
    with contextlib.closing(sqlite3.connect(old)) as store:
        store.executescript(f"BEGIN;\n{schema.MIGRATIONS[0]}PRAGMA user_version = 1;\nCOMMIT;")
    for path in (old, new):
        telemetry.connect(path).close()
        with contextlib.closing(sqlite3.connect(path)) as store:
            assert store.execute("PRAGMA user_version").fetchone() == (len(schema.MIGRATIONS),)
            for source in kept.SOURCES:
                columns = {row[1] for row in store.execute(f"PRAGMA table_info({source.table})")}
                assert {name for name, _ in source.columns} <= columns, source.table


def test_a_pass_logs_its_seconds_and_the_next_build_keeps_them_as_the_machines(kitchen):
    kitchen.poll()
    lines = (kitchen.state_dir / "passes.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert isinstance(json.loads(lines[0])["seconds"], float)
    kitchen.poll()
    with contextlib.closing(sqlite3.connect(kitchen.state_dir / telemetry.FILE)) as store:
        held = store.execute("SELECT project, seconds IS NOT NULL FROM passes").fetchall()
    assert held == [("", 1)]
