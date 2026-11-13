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
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from jbus import history, queue, telemetry
from jbus.telemetry import cursors, migrations, waits
from test_jbus_telemetry import NOW, SECRET, counted, iso, machine

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
    """The records of what jbus's snapshots overwrite, each read by its source:
    `jbus.telemetry.records.brief_versions`, `jbus.telemetry.records.row_pulls`,
    `jbus.telemetry.records.runs`, `jbus.telemetry.records.spend_days`,
    `jbus.telemetry.records.spend_rows` and `jbus.telemetry.records.word_sends`."""
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
    counted(path, 1)
    with contextlib.closing(sqlite3.connect(path)) as old:
        old.execute("INSERT INTO meta (name, value) VALUES ('kept', 'yes')")
        old.commit()
    kept(machine, "alpha", NOW)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert telemetry.ran(store) == set(migrations.MIGRATIONS)
        assert store.execute("SELECT value FROM meta WHERE name = 'kept'").fetchone() == ("yes",)
        assert store.execute("SELECT count(*) FROM runs").fetchone() == (2,)


def test_a_word_still_waiting_shows_as_waiting_with_no_thread(machine):
    kept(machine, "alpha", NOW)
    machine.write("alpha", "word-sends.json", {"w1": {"waits": "its home has no home-id"}})
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute("SELECT word, thread, sent_at, waiting FROM carried_words").fetchall()
    assert rows == [("w1", None, None, 1)]


def launch(machine, slug, sha, **record):
    """Write a launch record as jbus does, under `launches/<project>/<slug>/<sha>.json`."""
    path = machine.state_dir / "launches" / "alpha" / slug / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": f"alpha/{slug}/{sha}", **record}))
    return path


def test_launch_arms_keeps_each_launchs_arm_once_and_an_older_launch_reads_not_covered(machine):
    at = iso(NOW)
    launched = {"state": "launched", "thread": "mcp:t", "at": at}
    path = launch(machine, "one", "a" * 12, **launched, arms={"crew-router-pilot": "control"})
    launch(machine, "two", "b" * 12, **launched, role="scout", priming="trimmed")
    launch(machine, "three", "c" * 12, **launched)
    launch(machine, "four", "d" * 12, state="intent", at=at, arms={"crew-router-pilot": "off"})
    machine.build()
    query = "SELECT slug, role, dial, arm, covered, thread, at, day FROM launch_arms ORDER BY slug"
    stamp = "2026-10-28T15:00:00.000000Z"
    with contextlib.closing(machine.store()) as store:
        assert store.execute(query).fetchall() == [
            ("one", "crew", "crew-router-pilot", "control", 1, "mcp:t", stamp, "2026-10-28"),
            ("three", "crew", None, None, 0, "mcp:t", stamp, "2026-10-28"),
            ("two", "scout", "crew-router-pilot", "trimmed", 1, "mcp:t", stamp, "2026-10-28"),
        ]
    path.write_text(path.read_text())
    assert "nothing new" in machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute("SELECT count(*) FROM launch_arms").fetchone() == (3,)


def test_review_rounds_keeps_each_round_once_with_its_verdict_and_counts(machine):
    """`jbus.telemetry.records.review_rounds` keeps a round's verdict and its counts."""
    line = {
        "at": iso(NOW),
        "slug": "one",
        "pr": 7,
        "round": 2,
        "head": "c" * 40,
        "scoped": True,
        "sections": 1,
        "meets": "yes",
        "met": 3,
        "of": 3,
        "errors": 1,
        "warnings": 0,
        "infos": 2,
        "others": 0,
        "dismissed": 1,
    }
    machine.append("alpha", "review-rounds.jsonl", line)
    machine.build()
    query = (
        "SELECT slug, pr, round_number, head, scoped, sections, meets, met, done_when, errors, "
        "warnings, infos, others, dismissed FROM review_rounds"
    )
    row = ("one", 7, 2, "c" * 40, 1, 1, "yes", 3, 3, 1, 0, 2, 0, 1)
    with contextlib.closing(machine.store()) as store:
        assert store.execute(query).fetchall() == [row]
    other = {**line, "slug": "two"}
    path = machine.state("alpha") / "review-rounds.jsonl"
    path.write_text(f"{json.dumps(other)}\n{json.dumps(line)}\n")
    assert "review_rounds 1" in machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute(f"{query} WHERE slug = 'one'").fetchall() == [row]


ASKED = {"opens": "open one when done", "asks": "ask first", "none": "none, a probe"}


def brief(slug, asked):
    return f"# {slug}: a task\nDone when:\n- it holds\nPull request: {asked}\nReview: none\n"


def test_each_stored_brief_keeps_what_its_pull_request_line_asks(machine):
    for slug, asked in ASKED.items():
        queue._store(machine.state("alpha"), slug, brief(slug, asked))
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute("SELECT slug, pull FROM brief_versions ORDER BY slug").fetchall()
    assert rows == [("asks", "ask"), ("none", "none"), ("opens", "open")]


def test_a_line_written_before_pull_reads_it_from_its_kept_text_or_as_empty(machine):
    """A store read to the end of a log before `jbus.telemetry.migrations.v015_brief_pull` reads
    it again, and `jbus.telemetry.records` takes each old line's `pull` from its kept text, or
    keeps none where that text is gone."""
    path = machine.state_dir / telemetry.FILE
    counted(path, list(migrations.MIGRATIONS).index("v015_brief_pull"))
    state = machine.state("alpha")
    (state / history.KEPT).mkdir()
    (state / history.KEPT / f"{'a' * 64}.md").write_text(brief("kept", ASKED["opens"]))
    machine.append(
        "alpha",
        "brief-versions.jsonl",
        *(
            {"at": iso(NOW), "slug": slug, "sha": sha * 64, "was": "", "bytes": 80}
            for slug, sha in (("kept", "a"), ("gone", "b"))
        ),
    )
    log = state / "brief-versions.jsonl"
    with contextlib.closing(sqlite3.connect(path)) as old, open(log, "rb") as handle:
        at = (log.stat().st_ino, log.stat().st_size, cursors.head(handle))
        cursors.keep(old, "alpha", "brief_versions", at[0], at[1], at[2], at[1], None)
        old.commit()
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute("SELECT slug, pull FROM brief_versions ORDER BY slug").fetchall()
    assert rows == [("gone", None), ("kept", "open")]


def test_a_brief_version_keeps_the_outcome_its_close_names_and_an_older_line_none(machine):
    """A store built before `jbus.telemetry.migrations.v018_brief_outcome` gains `outcome` on its
    next build: a line `history.brief` wrote before it keeps none, and a version whose last Result
    names its row's end (`jbus.outcome`) keeps that end beside its `pull`."""
    counted(
        machine.state_dir / telemetry.FILE, list(migrations.MIGRATIONS).index("v018_brief_outcome")
    )
    state = machine.state("alpha")
    machine.append(
        "alpha",
        "brief-versions.jsonl",
        {"at": iso(NOW), "slug": "old", "sha": "a" * 64, "was": "", "bytes": 80, "pull": "open"},
    )
    closed = (
        "\n## Result\nStatus: done\nBranch: b   Pull request: none\nOutcome: dropped, unwanted\n"
    )
    queue._store(state, "new", brief("new", ASKED["opens"]) + closed)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute("SELECT slug, pull, outcome FROM brief_versions ORDER BY slug")
        assert rows.fetchall() == [("new", "open", "dropped"), ("old", "open", None)]


def test_the_queue_keeps_who_queued_each_row_and_the_message_its_go_rests_on(machine):
    """`jbus.telemetry.records.queue` fills `queued_by_session` and `approval_message` for each
    basis, as the text columns `jbus.telemetry.values` types them, and a store built before
    `jbus.telemetry.migrations.v014_queue_joins` gains both columns on its next build, and the
    queue's rows it already holds are read again to fill them."""
    home = {"directory": "/home/u/repo", "session": "home-session"}
    jbus = {"by": "jbus", "session": ""}
    goes = {
        "entry": ({"ref": "plan-entry", "message": "mcp:home/m-entry"}, "mcp:home/m-entry"),
        "message": ({"ref": "mcp:home/m-said"}, "mcp:home/m-said"),
        "pick": ({"ref": "mcp:home/m-picked"}, "mcp:home/m-picked"),
        "word": ({"ref": "w1", "message": "mcp:home/m-not"}, ""),
        "answer": ({"ref": "3"}, ""),
        "rule": ({"ref": "follow-up", "follows": "parent"}, ""),
        "page": ({"ref": "p1"}, ""),
        "bot-chat": ({"ref": "w2"}, ""),
    }
    rows = [
        {"slug": basis, "status": "queued", "queued_by": home, "approval": {"basis": basis, **go}}
        for basis, (go, _) in goes.items()
    ]
    rows.append({"slug": "filed", "status": "queued", "queued_by": jbus, "approval": {}})
    machine.write("alpha", "queue.json", rows)
    want = sorted(
        [
            *((basis, "home-session", message) for basis, (_, message) in goes.items()),
            ("filed", "", ""),
        ]
    )
    query = "SELECT slug, queued_by_session, approval_message FROM queue ORDER BY slug"
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute(query).fetchall() == want
        types = {name: kind for _, name, kind, *_ in store.execute("PRAGMA table_info(queue)")}
        assert (types["queued_by_session"], types["approval_message"]) == ("TEXT", "TEXT")
        views = [
            name for (name,) in store.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        ]
        store.executescript(
            "".join(f"DROP VIEW {name};" for name in views)
            + "ALTER TABLE queue DROP COLUMN queued_by_session;"
            + "ALTER TABLE queue DROP COLUMN approval_message;"
            + "DELETE FROM migrations WHERE name = 'v014_queue_joins';"
        )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute(query).fetchall() == want


def test_launch_waits_splits_a_rows_go_to_launch_by_the_kind_of_each_reason(machine):
    """The source `jbus.telemetry.records.row_waits`, its table in
    `jbus.telemetry.migrations.v014_row_waits` and the view `jbus.telemetry.views.launch_waits`.
    `one`'s go is at NOW, after `zero`'s line began the log:
    a minute with no line, ten on a slug it depends on, ten on a full /tmp, ten on its home's cap,
    then its launch. Its line after the launch, and `zero`, which never launched, count nothing."""
    from jbus import dispatch, roomwait

    minute = timedelta(minutes=1)
    machine.append(
        "alpha",
        "items.jsonl",
        {"id": "i1", "at": iso(NOW), "item": "i1", "verb": "approved", "slug": "one"},
    )
    machine.append(
        "alpha",
        "transitions.jsonl",
        {"slug": "one", "from": "queued", "to": "launched", "at": iso(NOW + 31 * minute)},
    )
    whys = (
        (-60, "zero", "not approved"),
        (1, "one", "depends on two"),
        (11, "one", "waiting: /tmp at 92% of its quota"),
        (21, "one", "max_per_home is 2 in the root home"),
        (31, "one", ""),
    )
    machine.append(
        "alpha",
        "waits.jsonl",
        *({"slug": slug, "why": why, "at": iso(NOW + at * minute)} for at, slug, why in whys),
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        split = store.execute(
            "SELECT slug, kind, seconds FROM launch_waits WHERE project = 'alpha' ORDER BY kind"
        ).fetchall()
        kept = store.execute("SELECT slug, kind, why_len FROM row_waits ORDER BY at").fetchall()
    assert split == [
        ("one", "cap", 600.0),
        ("one", "depends", 600.0),
        ("one", "none", 60.0),
        ("one", "room", 600.0),
    ]
    assert kept[0] == ("zero", "hold", len("not approved"))
    assert kept[-1] == ("one", "none", 0)
    said = {
        roomwait.ROOM: "room",
        f"{roomwait.ROOM}: load is at or over 85% of 12 cores": "room",
        "no launch: claudeAgent is capped until 2026-11-09T22:00:00+00:00": "room",
        "waiting: /tmp is full: its quota": "room",
        "waiting: /tmp at 81% of its quota": "room",
        f"{dispatch.HELD}: a settled thread already has this slug": "hold",
        "max_running is 4 across all projects": "cap",
        "max_per_project is 6 in jstack": "cap",
        "main is red: waits for green": "red main",
        dispatch.UNKNOWN: "none",
    }
    assert {why: waits.kind(why) for why in said} == said


def test_pass_steps_gives_each_step_of_each_pass_its_wall_and_cpu_seconds(machine):
    """A pass's line names each step's `[wall, cpu]` seconds; a step whose figures are not two
    numbers is left out, and a line from before the steps were timed has no step. The code is the
    migration `jbus.telemetry.migrations.v014_pass_steps`, the rows of `jbus.telemetry.machine`
    and the view `jbus.telemetry.views.pass_steps`."""
    lines = [
        {"at": iso(NOW), "seconds": 30.2},
        {
            "at": iso(NOW + timedelta(minutes=1)),
            "seconds": 31.0,
            "steps": {
                "first halves": [20.5, 18.25],
                "first halves/watch.look": [12.0, 1.5],
                "broken": [1.0],
            },
            "children": 9.75,
        },
    ]
    (machine.state_dir / "passes.jsonl").write_text(
        "".join(f"{json.dumps(one)}\n" for one in lines)
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        steps = store.execute(
            "SELECT project, at, step, seconds, cpu FROM pass_steps ORDER BY step"
        ).fetchall()
        children = store.execute("SELECT children FROM passes ORDER BY at").fetchall()
    at = iso(NOW + timedelta(minutes=1))
    assert [(project, step, seconds, cpu) for project, _, step, seconds, cpu in steps] == [
        ("", "first halves", 20.5, 18.25),
        ("", "first halves/watch.look", 12.0, 1.5),
    ]
    assert {when[:16] for _, when, *_ in steps} == {at[:16]}
    assert children == [(None,), (9.75,)]


def test_transitions_carry_whether_the_move_table_holds_the_move(machine):
    """A line `jbus.queue.derive` marked `"legal": false` reads 0 and any other 1, and a store
    built before `jbus.telemetry.migrations.v014_transitions_legal` gains the column on its next
    build, with each line it already holds read as 1, as a rebuild reads an unmarked line."""
    log = "transitions.jsonl"
    machine.append("alpha", log, {"slug": "one", "from": "pr", "to": "merged", "at": iso(NOW)})
    machine.build()
    with contextlib.closing(machine.store()) as store:
        views = [
            name for (name,) in store.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        ]
        store.executescript(
            "".join(f"DROP VIEW {name};" for name in views)
            + "ALTER TABLE transitions DROP COLUMN legal;"
            + "DELETE FROM migrations WHERE name = 'v014_transitions_legal';"
        )
    marked = {"slug": "two", "from": "merged", "to": "gate", "at": iso(NOW), "legal": False}
    machine.append("alpha", log, marked)
    machine.build()
    query = "SELECT slug, from_status, to_status, legal FROM transitions ORDER BY slug"
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(query).fetchall()
    assert rows == [("one", "pr", "merged", 1), ("two", "merged", "gate", 0)]


def test_transitions_carry_whether_the_move_hands_a_scouts_row_over(machine):
    """A line `jbus.queue._hand_over` marked `"handed": true` reads 1 and any other 0, and a store
    built before `jbus.telemetry.migrations.v023_transitions_handed` gains the column on its next
    build, with each line it already holds read as 0, as a rebuild reads an unmarked line."""
    log = "transitions.jsonl"
    machine.append("alpha", log, {"slug": "one", "from": "done", "to": "queued", "at": iso(NOW)})
    machine.build()
    with contextlib.closing(machine.store()) as store:
        views = [
            name for (name,) in store.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        ]
        store.executescript(
            "".join(f"DROP VIEW {name};" for name in views)
            + "ALTER TABLE transitions DROP COLUMN handed;"
            + "DELETE FROM migrations WHERE name = 'v023_transitions_handed';"
        )
    handed = {"slug": "two", "from": "done", "to": "queued", "at": iso(NOW), "handed": True}
    machine.append("alpha", log, handed)
    machine.append("alpha", log, {"slug": "three", "from": "done", "to": "removed", "at": iso(NOW)})
    machine.build()
    query = "SELECT slug, from_status, to_status, handed FROM transitions ORDER BY at, slug"
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(query).fetchall()
    assert sorted(rows) == [
        ("one", "done", "queued", 0),
        ("three", "done", "removed", 0),
        ("two", "done", "queued", 1),
    ]


def test_transitions_carry_whether_the_move_opens_a_reverted_row(machine):
    """A line `jbus.queue.reland` marked with the revert's address under `reverted` reads 1 and any
    other 0, and a store built before `jbus.telemetry.migrations.v024_transitions_reverted` gains
    the column on its next build, with each line it already holds read as 0."""
    log = "transitions.jsonl"
    machine.append("alpha", log, {"slug": "one", "from": "pr", "to": "merged", "at": iso(NOW)})
    machine.build()
    with contextlib.closing(machine.store()) as store:
        views = [
            name for (name,) in store.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        ]
        store.executescript(
            "".join(f"DROP VIEW {name};" for name in views)
            + "ALTER TABLE transitions DROP COLUMN reverted;"
            + "DELETE FROM migrations WHERE name = 'v024_transitions_reverted';"
        )
    revert = "https://example.test/pull/9"
    relanded = {"slug": "two", "from": "merged", "to": "left", "at": iso(NOW), "reverted": revert}
    machine.append("alpha", log, relanded)
    machine.append("alpha", log, {"slug": "three", "from": "merged", "to": "left", "at": iso(NOW)})
    machine.build()
    query = "SELECT slug, from_status, to_status, reverted FROM transitions"
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(query).fetchall()
    assert sorted(rows) == [
        ("one", "pr", "merged", 0),
        ("three", "merged", "left", 0),
        ("two", "merged", "left", 1),
    ]


def test_a_line_that_moves_a_rows_go_is_no_change_of_its_status(machine):
    """`jbus.queue._go` writes a row's go to `transitions.jsonl`, and the table keeps only the
    changes of status (`jbus.telemetry.records.transitions`): a go line between two of them would
    cut the time a row spent in one, which `hours-after-pr` sums."""
    log, at = "transitions.jsonl", iso(NOW)
    machine.append("alpha", log, {"slug": "one", "from": "queued", "to": "launched", "at": at})
    machine.append("alpha", log, {"slug": "one", "go": "held", "by": "user", "at": at})
    machine.append("alpha", log, {"slug": "one", "from": "launched", "to": "pr", "at": at})
    machine.build()
    query = "SELECT slug, from_status, to_status FROM transitions ORDER BY from_status"
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(query).fetchall()
    assert rows == [("one", "launched", "pr"), ("one", "queued", "launched")]


def test_a_store_from_before_health_readings_gains_the_table_and_reads_the_machines_log(machine):
    """A store migrated up to `jbus.telemetry.migrations.v016_health_readings` gains its table,
    and `jbus.telemetry.machine` reads each line of the machine's `health.jsonl` as the
    machine's row (`jbus.telemetry.records.health_readings`): a fraction of a quota as it is,
    a reading jbus could not take as null."""
    path = machine.state_dir / telemetry.FILE
    counted(path, list(migrations.MIGRATIONS).index("v016_health_readings"))
    with open(machine.state_dir / "health.jsonl", "w") as log:
        for key, value, over in (
            ("disk /", 19, False),
            ("quota claudeAgent seven_day", 81.5, True),
            ("timeout jbus", None, None),
        ):
            log.write(json.dumps({"at": iso(NOW), "key": key, "value": value, "over": over}) + "\n")
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(
            "SELECT project, reading, value, over FROM health_readings ORDER BY reading"
        ).fetchall()
    assert rows == [
        ("", "disk /", 19.0, 0),
        ("", "quota claudeAgent seven_day", 81.5, 1),
        ("", "timeout jbus", None, None),
    ]


def test_each_of_the_machines_logs_is_read_as_the_machines_rows(machine):
    """`jbus.telemetry.machine` reads the passes, the drift probes and the capped reads of jbus's
    own state as rows of the project `''`, each column as its writer gave it
    (`jbus.telemetry.records.passes`, `jbus.telemetry.records.drift` and
    `jbus.telemetry.records.capped_reads`)."""
    later = iso(NOW + timedelta(hours=2))
    for name, line in (
        ("passes.jsonl", {"at": iso(NOW), "seconds": 21.5}),
        ("drift.jsonl", {"at": iso(NOW), "probe": "p", "word": "w", "status": "held", "found": 2}),
        (
            "capped.jsonl",
            {"at": iso(NOW), "reader": "pass", "instances": ["a"], "capped": {"a": later}},
        ),
    ):
        (machine.state_dir / name).write_text(json.dumps(line) + "\n")
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert store.execute("SELECT project, seconds FROM passes").fetchall() == [("", 21.5)]
        assert store.execute("SELECT probe, status, found FROM drift").fetchall() == [
            ("p", "held", 2)
        ]
        assert store.execute(
            "SELECT reader, instances, capped, ends_at IS NOT NULL FROM capped_reads"
        ).fetchall() == [("pass", 1, 1, 1)]


def test_a_store_from_before_load_samples_gains_the_table_and_reads_jgauges_load_log(
    machine, monkeypatch
):
    """A store migrated up to `jbus.telemetry.migrations.v017_load_samples` gains its table, and
    a build reads jgauge's load.tsv where `JGAUGE_LOAD_LOG` names it, outside jbus's state, as
    the machine's rows (`jbus.telemetry.records.load_samples`): each row's time, cores and
    1-minute load, the header as a row with none, and an empty load as null."""
    path = machine.state_dir / telemetry.FILE
    counted(path, list(migrations.MIGRATIONS).index("v017_load_samples"))
    log = machine.root / "jgauge" / "load.tsv"
    log.parent.mkdir()
    monkeypatch.setenv("JGAUGE_LOAD_LOG", str(log))
    log.write_text("time\tcores\tload1\n1794278012\t24\t21.61\n1794278027\t24\t\n")
    machine.build()
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(
            "SELECT project, at, cores, load1 FROM load_samples ORDER BY at NULLS FIRST"
        ).fetchall()
    assert rows == [
        ("", None, None, None),
        ("", "2026-11-10T02:33:32.000000Z", 24, 21.61),
        ("", "2026-11-10T02:33:47.000000Z", 24, None),
    ]


def test_each_source_is_the_module_named_for_its_table():
    """A source is a module of `jbus.telemetry.records` named for its table, so a new source is
    a new file, and `SOURCES` holds one source of each module, in the order of their names."""
    import pkgutil

    from jbus.telemetry import records

    modules = sorted(found.name for found in pkgutil.iter_modules(records.__path__))
    assert [source.table for source in records.SOURCES] == modules


def test_a_stall_spell_is_kept_with_its_times_and_minutes(machine):
    """`jbus.telemetry.records.stalls` keeps a spell's thread, its times and its minutes, and a
    line with no minutes, as the line a spell begins with, as null minutes."""
    began = {"at": iso(NOW), "thread": "t-1", "role": "crew", "slug": "one", "since": iso(NOW)}
    ended = {**began, "at": iso(NOW + timedelta(minutes=9)), "minutes": 9, "became": "hung"}
    machine.append("alpha", "stalls.jsonl", began, ended)
    machine.build()
    with contextlib.closing(machine.store()) as store:
        found = store.execute(
            "SELECT thread, slug, since, minutes, became FROM stalls ORDER BY at"
        ).fetchall()
    since = "2026-10-28T15:00:00.000000Z"
    assert found == [("t-1", "one", since, None, None), ("t-1", "one", since, 9, "hung")]


def test_held_now_holds_each_open_wait_with_its_row_held_seconds_up_to_the_last_build(machine):
    """A spell open on `row-held` counts its open segment up to the last build; a pull request
    whose merge began at its head, or whose spell left `merge-waits.json`, waits no more. The
    spells are read by `jbus.telemetry.records.open_waits` into the table that
    `jbus.telemetry.migrations.v017_open_waits` makes, and `jbus.telemetry.views.held_now` reads
    it."""
    seen = (datetime.now(UTC) - timedelta(minutes=10)).replace(microsecond=0)
    spells = {
        str(number): {
            "head": head,
            "ready": iso(seen - timedelta(hours=1)),
            "ready_by": "check",
            "seen": iso(seen),
            "code": code,
            "blockers": {"row-held": 100, "undecided": 40},
        }
        for number, head, code in ((1, "h1", "row-held"), (2, "h2", "undecided"), (3, "h3", ""))
    }
    waits_file = machine.home_dir / "alpha" / "merge-waits.json"
    waits_file.write_text(json.dumps(spells))
    machine.append(
        "alpha",
        "merge-waits.jsonl",
        {
            "at": iso(seen),
            "number": 2,
            "head": "h2",
            "ready": iso(seen),
            "ready_by": "check",
            "began": iso(seen),
            "seconds": 140,
            "blockers": {},
        },
        home=True,
    )
    machine.build()
    query = "SELECT pr, held FROM held_now WHERE project = 'alpha' ORDER BY pr"
    with contextlib.closing(machine.store()) as store:
        (built,) = store.execute("SELECT max(at) FROM builds").fetchone()
        found = store.execute(query).fetchall()
    open_for = (datetime.fromisoformat(built.replace("Z", "+00:00")) - seen).total_seconds()
    assert [pr for pr, _ in found] == [1, 3]
    assert found[0][1] == pytest.approx(100 + open_for, abs=0.01)
    assert found[1][1] == 100

    del spells["3"]
    waits_file.write_text(json.dumps(spells))
    machine.build()
    with contextlib.closing(machine.store()) as store:
        assert [pr for pr, _ in store.execute(query)] == [1]
