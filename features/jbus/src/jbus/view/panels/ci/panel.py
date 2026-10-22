"""The nine targets of CI, each with its value now, the target it is held to, how jbus counted
it, and its series by day. The series has a mark at the merge of each change that was meant to
move the target.

The panel reads everything from `ci.jsonl` and `ci-prs.jsonl` of the project's state, which
`jbus ci` writes (`jbus.ci`). The numbers are the ones `jbus ci` prints, because the same
functions count them: over the last `DAYS` days, and over each of those days for the series. The
marks are the merges that `merge.log` records: the three levers of the plan in this project's
home, and the change of the runner's CPUs in the home of the project that owns the runner.

The page asks for this panel when its drawer opens, at `/panel/ci.json`. The card on the first
screen says nothing that the ledger holds.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any

from jbus.ci import numbers
from jbus.view import state
from jbus.view.state import Read, Spot, iso, kept

FIRST = False
DAYS = 14
MARKS = (
    ("ci-one-suite-per-tree", "one suite per tree", None),
    ("ci-slow-tail", "slow tail", None),
    ("ci-test-map", "test map", None),
    ("jstack-fast-4", "runner CPUs to 4", "infra"),
)
_NUMBER = {
    "key": None,
    "name": None,
    "value": None,
    "shown": None,
    "target": None,
    "met": None,
    "n": None,
    "how": None,
    "hosted": None,
    "series": [{"day": None, "value": None}],
}
SHAPE = {
    "ci": {
        "read": None,
        "from": None,
        "to": None,
        "days": None,
        "jobs": None,
        "numbers": [_NUMBER],
        "marks": [{"label": None, "at": None, "project": None}],
    }
}
SOURCES = (
    kept("ci.jsonl", lambda read: read.records("ci.jsonl"), 170),
    kept("ci-prs.jsonl", lambda read: read.records("ci-prs.jsonl"), 171),
)
NOT_KEPT = (Spot("the /tmp inode series is not kept until a job writes tmp_inode_pct", 530),)


def blind(read: Read) -> list[Spot]:
    return []


def marks(read: Read) -> list[dict[str, Any]]:
    """The merge of each change of `MARKS` that `merge.log` records as merged."""
    found = []
    homes: dict[str | None, dict[str, tuple[int, str]]] = {
        None: state._landed(read.log or [], read.user)
    }
    for slug, label, project in MARKS:
        if project not in homes:
            homes[project] = state._landed(
                state._lines(read.sources.home(project) / "merge.log") or [], read.user
            )
        landed = homes[project].get(slug)
        if landed:
            found.append({"label": label, "at": landed[1], "project": project or read.name})
    return found


def build(read: Read) -> dict[str, Any]:
    jobs, pulls = read.records("ci.jsonl"), read.records("ci-prs.jsonl")
    now = read.now
    start = now - timedelta(days=DAYS)
    base = {"read": jobs is not None, "from": iso(start), "to": iso(now), "days": DAYS}
    if jobs is None:
        return {"ci": base | {"jobs": 0, "numbers": [], "marks": marks(read)}}
    facts = numbers.Facts(jobs, pulls or [], read.logged or [], now)
    nine = numbers.compute(facts, start, now)
    days = numbers.day_windows(now, DAYS, read.user.zone or UTC)
    by_day = {name: numbers.compute(facts, first, last) for name, first, last in days}
    return {
        "ci": base
        | {
            "jobs": len(jobs),
            "numbers": [
                {
                    "key": one.key,
                    "name": one.name,
                    "value": one.value,
                    "shown": one.shown,
                    "target": one.target,
                    "met": one.met,
                    "n": one.n,
                    "how": one.how,
                    "hosted": one.hosted,
                    "series": [
                        {"day": name, "value": by_day[name][at].value} for name, _, _ in days
                    ],
                }
                for at, one in enumerate(nine)
            ],
            "marks": marks(read),
        }
    }
