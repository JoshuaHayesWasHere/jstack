"""The telemetry store reads the records jbus keeps of what its snapshots overwrite, and the
carried words from `acts.jsonl` and `word-sends.json`, and answers the week audit's data faults.

Each fault has one query, the one the store's page (`the-telemetry-store.md`) gives:

- F1, no brief history: the brief each launch saw, and the versions after it.
- F2, the latest CI attempt only: every attempt of every project's runs.
- F3, one pull request per row: each row's every pull request.
- F4, carried words missing: each word a home carried, from `acts.jsonl`.
- F5, no tokens per row: each row's spend by role and day.
- F8, spend stored nowhere: one row of spend a day.
"""

import contextlib
import sqlite3
from datetime import timedelta

from jbus import telemetry
from jbus.telemetry import schema
from test_jbus_telemetry import NOW, SECRET, iso, machine

__all__ = ["machine"]

NEW = ("brief_versions", "row_pulls", "runs", "spend_days", "spend_rows", "word_sends")
FAULTS = {
    "F1": "SELECT slug, launched_at, sha, changed_after FROM brief_at_launch "
    "WHERE project = 'alpha' ORDER BY launched_at",
    "F2": "SELECT run, attempts, first_fail_attempt, last_conclusion FROM run_attempts "
    "WHERE project = 'alpha' ORDER BY run",
    "F3": "SELECT slug, group_concat(number, ' ') FROM (SELECT DISTINCT project, slug, number "
    "FROM row_pulls ORDER BY number) WHERE project = 'alpha' GROUP BY project, slug",
    "F4": "SELECT word, said_in, source, thread, waiting, words_len FROM carried_words "
    "WHERE project = 'alpha' ORDER BY kept_at",
    "F5": "SELECT spent_on, role, slug, units FROM spend_rows "
    "WHERE project = 'alpha' AND slug IS NOT NULL ORDER BY spent_on, role, slug",
    "F8": "SELECT spent_on, units, runs, first, reviews FROM spend_days "
    "WHERE project = 'alpha' ORDER BY spent_on",
}


def kept(machine, project, at):
    """Write each record as its writer writes it, for a row `one` launched once, whose brief
    changed after its launch, which had two pull requests, and whose check failed once."""
    one, two = "a" * 64, "b" * 64
    machine.append(
        project,
        "transitions.jsonl",
        {"slug": "one", "from": "queued", "to": "launched", "at": iso(at + timedelta(minutes=5))},
    )
    machine.append(
        project,
        "brief-versions.jsonl",
        {"at": iso(at), "slug": "one", "sha": one, "was": "", "bytes": 300},
        {"at": iso(at + timedelta(hours=1)), "slug": "one", "sha": two, "was": one, "bytes": 320},
    )
    machine.append(
        project,
        "row-pulls.jsonl",
        *(
            {
                "at": iso(at + timedelta(minutes=minute)),
                "slug": "one",
                "number": number,
                "state": state,
                "branch": "one",
                "head": "c" * 40,
                "merged_at": iso(at + timedelta(minutes=minute)) if state == "merged" else None,
            }
            for minute, number, state in ((10, 7, "open"), (40, 9, "open"), (90, 9, "merged"))
        ),
    )
    machine.append(
        project,
        "runs.jsonl",
        *(
            {
                "at": iso(at + timedelta(minutes=20 * attempt)),
                "run": 501,
                "attempt": attempt,
                "workflow": "check",
                "sha": "c" * 40,
                "branch": "one",
                "event": "pull_request",
                "pr": 9,
                "created": iso(at),
                "started": iso(at + timedelta(minutes=20 * attempt - 10)),
                "updated": iso(at + timedelta(minutes=20 * attempt)),
                "conclusion": conclusion,
            }
            for attempt, conclusion in ((1, "failure"), (2, "success"))
        ),
    )
    day = at.date().isoformat()
    machine.append(
        project,
        "spend.jsonl",
        {
            "day": day,
            "at": iso(at + timedelta(days=1)),
            "units": 300,
            "runs": 3,
            "input": 1,
            "cached": 1,
            "written": 1,
            "output": 1,
            "first": 100,
            "reviews": 200,
        },
    )
    machine.append(
        project,
        "spend-rows.jsonl",
        {"day": day, "at": iso(at), "role": "crew", "slug": "one", "units": 100, "runs": 1},
        {"day": day, "at": iso(at), "role": "other", "slug": "", "units": 0, "runs": 1},
        {"day": day, "at": iso(at), "role": "review", "slug": "one", "units": 200, "runs": 1},
    )
    machine.append(
        project,
        "acts.jsonl",
        {
            "action": {"doors": [], "subject": "", "verb": "word"},
            "at": iso(at),
            "evidence": {
                "words": SECRET,
                "said_at": "2026-10-28 11:00 ET",
                "said_in": "home: root",
                "source": "t3-message",
                "ref": "mcp:x/y",
                "picks": [],
            },
            "id": "w1",
            "line": "kept",
            "outcome": "done",
            "party": {"kind": "home", "name": "", "route": "cli"},
        },
    )
    machine.write(project, "word-sends.json", {"w1": {"sent_at": iso(at), "thread": "mcp:home"}})


def test_the_store_reads_each_record_and_a_rebuild_reads_the_same(machine):
    kept(machine, "alpha", NOW)
    kept(machine, "beta", NOW)
    machine.build()
    assert "nothing new" in machine.build()

    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    with (
        contextlib.closing(machine.store()) as store,
        contextlib.closing(machine.store(machine.root / "again.sqlite")) as again,
    ):
        for table in NEW:
            rows = sorted(store.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
            assert rows, table
            assert rows == sorted(again.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
        counts = dict(store.execute("SELECT 'runs', count(*) FROM runs WHERE project = 'beta'"))
        assert counts == {"runs": 2}
    assert SECRET.encode() not in (machine.state_dir / telemetry.FILE).read_bytes()


def test_the_store_answers_each_of_the_audits_data_faults(machine):
    kept(machine, "alpha", NOW)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        found = {name: store.execute(sql).fetchall() for name, sql in FAULTS.items()}
    launched = "2026-10-28T15:05:00.000000Z"
    assert found["F1"] == [("one", launched, "a" * 64, 1)]
    assert found["F2"] == [(501, 2, 1, "success")]
    assert found["F3"] == [("one", "7 9")]
    assert found["F4"] == [("w1", "home: root", "t3-message", "mcp:home", 0, len(SECRET))]
    assert found["F5"] == [("2026-10-28", "crew", "one", 100), ("2026-10-28", "review", "one", 200)]
    assert found["F8"] == [("2026-10-28", 300, 3, 100, 200)]


def test_a_store_of_the_first_schema_gains_the_records_tables_and_keeps_its_rows(machine):
    path = machine.state_dir / telemetry.FILE
    with contextlib.closing(sqlite3.connect(path)) as old:
        old.executescript(f"BEGIN;\n{schema.MIGRATIONS[0]}PRAGMA user_version = 1;\nCOMMIT;")
        old.execute("INSERT INTO meta (name, value) VALUES ('kept', 'yes')")
        old.commit()
    kept(machine, "alpha", NOW)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute("PRAGMA user_version").fetchone() == (len(schema.MIGRATIONS),)
        assert store.execute("SELECT value FROM meta WHERE name = 'kept'").fetchone() == ("yes",)
        assert store.execute("SELECT count(*) FROM runs").fetchone() == (2,)


def test_a_word_still_waiting_shows_as_waiting_with_no_thread(machine):
    kept(machine, "alpha", NOW)
    machine.write("alpha", "word-sends.json", {"w1": {"waits": "its home has no home-id"}})
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute("SELECT word, thread, sent_at, waiting FROM carried_words").fetchall()
    assert rows == [("w1", None, None, 1)]
