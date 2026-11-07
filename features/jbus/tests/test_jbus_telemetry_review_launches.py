"""`review_launches` gives one row per reviewer thread, with the state of `check` at its head
when it launched, so how many reviews launched on a passed head, and the lag from push to launch,
is one query.

The test writes what the agents and jbus write: a reviewer's transcript under a T3 thread titled
`review: <slug>`, and jbus's `ci-prs.jsonl`, `row-pulls.jsonl` and `runs.jsonl`. It runs the real
`jbus telemetry` and reads the view as a reader would.
"""

import json
from datetime import timedelta

from test_jbus_telemetry_tokens import NOW, iso, machine, said

__all__ = ["machine"]


def reviewed(machine, slug, session, launched, ended):
    """A reviewer thread of the row `slug`, with a call at `launched` and one at `ended`."""
    machine.thread(f"mcp:review-{slug}", f"review: {slug}", "claudeAgent", session)
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
