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
from datetime import timedelta

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


def test_the_queue_keeps_who_queued_each_row_and_the_message_its_go_rests_on(machine):
    """`jbus.telemetry.records` fills `queued_by_session` and `approval_message` for each basis,
    as the text columns `jbus.telemetry.values` types them, and a store built before
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
    """The source `row_waits` of `jbus.telemetry.records`, its table in
    `jbus.telemetry.migrations.v014_row_waits` and the view `jbus.telemetry.views.launch_waits`.
    `one`'s go is at NOW, after `zero`'s line began the log:
    a minute with no line, ten on a slug it depends on, ten on a full /tmp, ten on its home's cap,
    then its launch. Its line after the launch, and `zero`, which never launched, count nothing."""
    from jbus import dispatch

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
        dispatch.ROOM: "room",
        "no launch: claudeAgent is capped until 2026-11-09T22:00:00+00:00": "room",
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
    machine.append(
        "alpha",
        "transitions.jsonl",
        {"slug": "one", "from": "pr", "to": "merged", "at": iso(NOW)},
        {"slug": "two", "from": "merged", "to": "gate", "at": iso(NOW), "legal": False},
    )
    machine.build()
    query = "SELECT slug, from_status, to_status, legal FROM transitions ORDER BY slug"
    with contextlib.closing(machine.store()) as store:
        rows = store.execute(query).fetchall()
    assert rows == [("one", "pr", "merged", 1), ("two", "merged", "gate", 0)]
