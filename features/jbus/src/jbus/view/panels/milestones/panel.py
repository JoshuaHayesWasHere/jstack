"""How close each milestone is to done, drawn as a chain of steps toward its outcome.

A milestone is an entry of a home's plan: a `## <slug>: <one line>` section of a home's
`plan.md`, the root's first and then each scope's by name, and its one line is the outcome it
names. A scope with no plan has no entries.

The panel counts a milestone's rows with `jbus plan`'s own count (`plan.progress`), and gives an
entry the line `jbus plan` prints for it (`plan.status`), so the bar and the words are one count.

Each row is a step of the chain, in the order its `depends` give, and among steps that depend on
none of each other, the ones further along first. A step's mark is the group `state.RANK` puts
the value the last pass judged in: `merged`, `working`, `waiting` (on a reviewer or a
check), `queued`, `needs you`, or `stuck` (a thread hung or lost, a pull request closed, a state
no pass could work out). A step that waits on another row is `blocked`, and says on which. A row
with no task is `merged` where the queue counts it as over, and `stuck` otherwise, as an unknown
state is.

`holder` is the step that holds the chain: the first stuck or needs-you step, else the first
blocked one, with what the last pass said of it. `waits_on` is each other milestone that a step
of this chain waits on, by a row of it that is not over. A row's milestone is its plan entry,
and nothing where it is in none.

The panel reads the plans and the queue each time it is asked, and writes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jbus import plan, queue
from jbus.view.state import (
    ASKS,
    BROKEN,
    OVER,
    QUEUE_FILE,
    QUEUED,
    RANK,
    STEP,
    WAITS,
    WORKS,
    Read,
    text,
)

FIRST = False
_COUNT = {"word": None, "count": None}
_PULL = {"pr": None, "word": None}
_STEP = {
    "slug": None,
    "status": None,
    "pr": None,
    "step": None,
    "mark": None,
    "say": None,
    "by": None,
    "depends": [None],
}
_WAITS = {"milestone": None, "slug": None, "mark": None}
_HOLDER = {"slug": None, "mark": None, "say": None, "by": None}
_CHAIN = {
    "key": None,
    "total": None,
    "over": None,
    "finished": [_COUNT],
    "pulls": [_PULL],
    "rest": [_COUNT],
    "steps": [_STEP],
    "holder": _HOLDER,
    "waits_on": [_WAITS],
}
_ENTRY = {"slug": None, "line": None, "status": None} | _CHAIN
_HOME = {"name": None, "plan": None, "entries": [_ENTRY]}
SHAPE = {"milestones": {"homes": [_HOME]}}
SOURCES = (QUEUE_FILE,)
MARK = {
    BROKEN: "stuck",
    ASKS: "needs you",
    WORKS: "working",
    WAITS: "waiting",
    QUEUED: "queued",
    OVER: "merged",
}
BLOCKED = "blocked"
_ALONG = ("merged", "waiting", "working", "needs you", "stuck", BLOCKED, "queued")
_HOLDS = ("stuck", "needs you", BLOCKED)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def _tasks(read: Read) -> dict[str, dict[str, Any]]:
    return {one["slug"]: one for one in (*read.tasks, *read.ended)}


def _step(read: Read, row: queue.Row) -> dict[str, Any]:
    """One row as a step of a chain: its status and pull request, the step of the line it is on,
    its mark, what the last pass said of it, and the row it waits on where it waits on one."""
    task = read.once(_tasks).get(row["slug"])
    if task is None:
        over = queue.over(row)
        mark, name, say, by = MARK[OVER if over else BROKEN], "Merged" if over else "", "", ""
    else:
        kind = task["state"]["kind"]
        blocked = task.get("blocked") or {}
        by = blocked.get("by", "") if kind == "behind" else ""
        mark = BLOCKED if by else MARK[RANK.get(kind, BROKEN)]
        name = STEP[task["step"]].name if task["step"] in STEP else ""
        say = task["state"].get("say", "")
    return {
        "slug": text(row["slug"], 80),
        "status": text(row.get("status", "queued"), 20),
        "pr": text(row.get("pr"), 20),
        "step": name,
        "mark": mark,
        "say": text(say, 160),
        "by": text(by, 80),
        "depends": [text(one, 80) for one in row.get("depends") or []],
    }


def _ordered(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The steps with each one after the steps of the chain it depends on, and the ones further
    along first among those free to go."""
    left = {one["slug"]: one for one in steps}
    order: list[dict[str, Any]] = []
    while left:
        free = [one for one in left.values() if not set(one["depends"]) & set(left)] or list(
            left.values()
        )
        first = min(free, key=lambda one: (_ALONG.index(one["mark"]), steps.index(one)))
        order.append(left.pop(first["slug"]))
    return order


def _chain(read: Read, key: str, rows: list[queue.Row], owner: dict[str, str]) -> dict[str, Any]:
    """A milestone's count, its steps in order, the step that holds it, and the other
    milestones it waits on. `owner` gives the milestone of each row of the queue."""
    counted = plan.progress(rows)
    steps = _ordered([_step(read, row) for row in rows])
    holds = next((one for mark in _HOLDS for one in steps if one["mark"] == mark), None)
    mine = {row["slug"] for row in rows}
    rows_by = {row["slug"]: row for row in read.rows}
    waits = {}
    for one in steps:
        for slug in one["depends"]:
            there = rows_by.get(slug)
            if slug in mine or (there is not None and queue.over(there)):
                continue
            milestone = owner.get(slug, "")
            if milestone != key:
                waits.setdefault((milestone, slug), _step(read, there)["mark"] if there else "")
    return {
        "key": key,
        "total": counted.total,
        "over": counted.over,
        "finished": [{"word": word, "count": count} for word, count in counted.finished],
        "pulls": [{"pr": pr, "word": word} for pr, word in counted.pulls],
        "rest": [{"word": word, "count": count} for word, count in counted.rest],
        "steps": steps,
        "holder": holds and {name: holds[name] for name in _HOLDER},
        "waits_on": [
            {"milestone": milestone, "slug": slug, "mark": mark}
            for (milestone, slug), mark in waits.items()
        ],
    }


def _wheres(read: Read) -> list[tuple[str, Path]]:
    return [("", read.home)] + [(scope.name, scope) for scope, _, _ in read.homes.scopes]


def _entry_of(read: Read) -> dict[str, str]:
    """The plan entry of each row of the queue whose entry is in a home's plan."""
    slugs = {
        one.slug
        for _, where in _wheres(read)
        for one in plan.entries(_read(where / "plan.md") or "")
    }
    return {row["slug"]: queue.entry(row) for row in read.rows if queue.entry(row) in slugs}


def _home(read: Read, name: str, where: Path) -> dict[str, Any]:
    """The entries of one home's plan, or none, with `plan` saying whether it has one."""
    said = _read(where / "plan.md")
    if said is None:
        gone = not (where / "plan.md").exists()
        return {"name": name, "plan": "missing" if gone else "unreadable", "entries": []}
    owner = read.once(_entry_of)
    entries = []
    for one in plan.entries(said):
        rows = plan.rows_of(one.slug, read.rows)
        entries.append(
            {"slug": one.slug, "line": text(one.line, 160), "status": text(plan.status(one, rows))}
            | _chain(read, one.slug, rows, owner)
        )
    return {"name": name, "plan": "read", "entries": entries}


def build(read: Read) -> dict[str, Any]:
    homes = [_home(read, name, where) for name, where in _wheres(read)]
    return {"milestones": {"homes": homes}}
