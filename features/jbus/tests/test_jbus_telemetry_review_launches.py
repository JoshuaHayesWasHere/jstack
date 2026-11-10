"""`review_launches` (`jbus.telemetry.views.review_launches`) gives one row per reviewer thread,
with the state of `check` at its head when it launched, so how many reviews launched on a passed
head, and the lag from push to launch, is one query.

The test writes what the agents and jbus write: a reviewer's transcript under a T3 thread titled
`review: <slug>`, and jbus's `ci-prs.jsonl`, `row-pulls.jsonl` and `runs.jsonl`. It runs the real
`jbus telemetry` and reads the view as a reader would.
"""

import json
from datetime import UTC, timedelta

import jsettings
from jbus.telemetry import measures
from jbus.telemetry.measures import m49_duplicate_reviews as duplicates

from test_jbus_telemetry_tokens import NOW, iso, machine, said

__all__ = ["machine"]


def reviewed(machine, slug, session, launched, ended, thread=None):
    """A reviewer thread of the row `slug`, with a call at `launched` and one at `ended`."""
    machine.thread(thread or f"mcp:review-{slug}", f"review: {slug}", "claudeAgent", session)
    machine.claude(
        session,
        said(launched, f"{session}-1", (1, 10, 100, 2), session=session),
        said(ended, f"{session}-2", (3, 20, 200, 4), session=session),
    )


def stored(moment):
    """A time as the store keeps it, to the microsecond."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def lines(machine, name, *records):
    with open(machine.state_dir / "alpha" / name, "a") as handle:
        handle.writelines(json.dumps(record) + "\n" for record in records)


def check(branch, pr, sha, created, conclusion, updated, attempt=1, started=None):
    return {
        "at": iso(updated),
        "run": ord(sha[0]),
        "attempt": attempt,
        "workflow": "check",
        "sha": sha,
        "branch": branch,
        "event": "pull_request",
        "pr": pr,
        "created": iso(created),
        "started": iso(started or created),
        "updated": iso(updated),
        "conclusion": conclusion,
    }


def opened(number, branch, created):
    return {"number": number, "branch": branch, "created": iso(created), "pushes": []}


def test_each_reviewer_launch_has_its_pull_request_and_checks_state_at_its_head(machine):
    minute = timedelta(minutes=1)
    reviewed(machine, "early", "s1", NOW, NOW + 2 * minute)
    reviewed(machine, "green", "s2", NOW + 30 * minute, NOW + 33 * minute)
    reviewed(machine, "red", "s3", NOW + 30 * minute, NOW + 31 * minute)
    reviewed(machine, "busy", "s4", NOW + 30 * minute, NOW + 32 * minute)
    machine.thread("mcp:crew-green", "crew: green", "claudeAgent", "s5")
    machine.claude("s5", said(NOW, "s5-1", (1, 1, 1, 1), session="s5"))
    lines(
        machine,
        "ci-prs.jsonl",
        opened(1, "early", NOW + 5 * minute),
        opened(2, "green", NOW),
        opened(3, "claude/red-branch", NOW),
        opened(4, "busy", NOW),
    )
    lines(
        machine,
        "row-pulls.jsonl",
        {
            "at": iso(NOW),
            "slug": "red",
            "number": 3,
            "state": "open",
            "branch": "claude/red-branch",
        },
    )
    lines(
        machine,
        "runs.jsonl",
        check("early", 1, "e" * 40, NOW + 5 * minute, "success", NOW + 15 * minute),
        check("green", 2, "a" * 40, NOW, "failure", NOW + 10 * minute),
        check("green", 2, "b" * 40, NOW + 12 * minute, "success", NOW + 24 * minute),
        check("claude/red-branch", None, "c" * 40, NOW + 10 * minute, "failure", NOW + 20 * minute),
        check(
            "claude/red-branch",
            None,
            "c" * 40,
            NOW + 10 * minute,
            "success",
            NOW + 45 * minute,
            attempt=2,
            started=NOW + 35 * minute,
        ),
        check("busy", 4, "d" * 40, NOW + 25 * minute, "success", NOW + 37 * minute),
    )

    machine.run()

    with machine.store() as store:
        rows = store.execute(
            "SELECT slug, pr, launched, ended, tokens, head, check_state, lag_minutes "
            "FROM review_launches ORDER BY slug"
        ).fetchall()
        green = store.execute(
            "SELECT count(*) FROM review_launches WHERE check_state = 'success'"
        ).fetchone()

    def at(minutes):
        return stored(NOW + minutes * minute)

    assert rows == [
        ("busy", 4, at(30), at(32), 340, "d" * 40, "running", 5.0),
        ("early", None, at(0), at(2), 340, None, None, None),
        ("green", 2, at(30), at(33), 340, "b" * 40, "success", 18.0),
        ("red", 3, at(30), at(31), 340, "c" * 40, "failure", 20.0),
    ]
    assert green == (1,)


def test_a_launch_repeats_another_only_where_both_have_the_same_head(machine):
    """Two reviewers of a slug launched before its pull request opened have no head, and are no
    repeat of each other; a second reviewer at the head the first one judged is one."""
    minute = timedelta(minutes=1)
    reviewed(machine, "early", "s1", NOW, NOW + minute, "mcp:early-1")
    reviewed(machine, "early", "s2", NOW + 10 * minute, NOW + 11 * minute, "mcp:early-2")
    reviewed(machine, "twice", "s3", NOW + 10 * minute, NOW + 11 * minute, "mcp:twice-1")
    reviewed(machine, "twice", "s4", NOW + 20 * minute, NOW + 21 * minute, "mcp:twice-2")
    lines(machine, "ci-prs.jsonl", opened(1, "early", NOW + 30 * minute), opened(2, "twice", NOW))
    lines(machine, "runs.jsonl", check("twice", 2, "a" * 40, NOW, "success", NOW + 5 * minute))

    machine.run()

    with machine.store() as store:
        rows = store.execute(
            "SELECT thread, head, again FROM review_launches ORDER BY thread"
        ).fetchall()
        repeats = store.execute("SELECT count(*) FROM review_launches WHERE again > 0").fetchone()

    assert rows == [
        ("mcp:early-1", None, 0),
        ("mcp:early-2", None, 0),
        ("mcp:twice-1", "a" * 40, 0),
        ("mcp:twice-2", "a" * 40, 1),
    ]
    assert repeats == (1,)


def launch(slug, thread, head, at, kind="first", n=1):
    """A line of `review-launches.jsonl`, as `jbus.reviewlaunch.record` writes it."""
    return {"at": iso(at), "slug": slug, "thread": thread, "head": head, "kind": kind, "n": n}


def test_duplicate_reviews_counts_the_launches_at_a_head_jbus_recorded(machine):
    """Two reviewers launched before their pull request, with no head on record, are no repeat of
    each other. Of three launches with a head on record, the second at the head the first was
    launched at is a repeat, and the third, at a head whose `check` run had not started when it
    launched, is none: the measure reads 1 of 3, and says 2 launches had no head on record."""
    minute = timedelta(minutes=1)
    reviewed(machine, "early", "s1", NOW, NOW + minute, "mcp:early-1")
    reviewed(machine, "early", "s2", NOW + 10 * minute, NOW + 11 * minute, "mcp:early-2")
    reviewed(machine, "twice", "s3", NOW + 2 * minute, NOW + 3 * minute, "mcp:twice-1")
    reviewed(machine, "twice", "s4", NOW + 10 * minute, NOW + 11 * minute, "mcp:twice-2")
    reviewed(machine, "twice", "s5", NOW + 21 * minute, NOW + 22 * minute, "mcp:twice-3")
    lines(machine, "ci-prs.jsonl", opened(1, "early", NOW + 30 * minute), opened(2, "twice", NOW))
    lines(
        machine,
        "runs.jsonl",
        check("twice", 2, "a" * 40, NOW + 5 * minute, "success", NOW + 8 * minute),
        check("twice", 2, "b" * 40, NOW + 25 * minute, "success", NOW + 28 * minute),
    )
    lines(
        machine,
        "review-launches.jsonl",
        launch("twice", "mcp:twice-1", "a" * 40, NOW + 2 * minute),
        launch("twice", "mcp:twice-2", "a" * 40, NOW + 10 * minute),
        launch("twice", "mcp:twice-3", "b" * 40, NOW + 21 * minute, kind="scoped"),
    )

    machine.run()

    with machine.store() as store:
        rows = store.execute(
            "SELECT thread, head, check_state, again FROM review_launches ORDER BY thread"
        ).fetchall()
        reading = measures.read(
            store, duplicates.MEASURE, "alpha", NOW + 60 * minute, jsettings.Settings(zone=UTC)
        )

    assert rows == [
        ("mcp:early-1", None, None, 0),
        ("mcp:early-2", None, None, 0),
        ("mcp:twice-1", "a" * 40, "queued", 0),
        ("mcp:twice-2", "a" * 40, "success", 1),
        ("mcp:twice-3", "b" * 40, "queued", 0),
    ]
    assert (reading.value, reading.n) == (1, 3)
    assert reading.note == "2 of 5 launches have no recorded head"
