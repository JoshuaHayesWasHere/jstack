"""The pipeline: every open row of every project and home, placed in its stage of the process,
with the chains its rows make and what holds the line.

`STAGES` are the stages in the order of the process. A task is in `you` when it is a need of the
You panel, an item of jbus's list of what waits on the user, and `you` counts every need of that
panel, a need that names no row too, so it is the one count every Needs-you widget gives. Any
other task is placed by the step the last pass gave it (`STAGE_OF_STEP`): a gate on its default
is the crew's, which carries on, and a hold jbus does not list is the merge's. On the step
`running`, who holds the task decides (`RUNNING_BY_WHO`), and a hung, waiting or lost thread is
the crew's still, since jbus lists no such thread as the user's. A task on no step the view
knows is `unplaced`. A task on the step `check` whose outcome is `stacked` (`checked.outcome`),
a pull request that merges after its parent row, is in `stacked` and not in `check`. A scout's
row (`queue.role`) is in `scout` from its launch until its request has a Report
(`state.request`). `merged` is a count of what merged today, into the default branch or an
integration branch alike, and has no rows: a row merged is done as far as the queue goes,
whatever branch it merged into.

A row's `cause`, `cause_since` and `moving` are what `cause.cause` says of its task, and its
`cause_kind` is the value the last pass judged (`work.VALUES`). Its `wait` is what a row on the
step `check` waits on, the outcome `checked.outcome` gives it (`failing`, `waiting`, `passed`,
`stacked`, or None where it has none), in `check`, in `stacked` and in `you` alike, so a stacked
row the user holds still counts as stacked, and None for a row on any other step. Its
`home` is its brief's, as `homes.Homes` gives it from `jbriefs.home_of`: a row whose brief names
no home, as a cleanup brief names none, is the root's, `root`, whatever rows it links to.

A row waits on each row its `depends` and `merge_after` name that is still open: a task of its
project, so not merged, done or judged through. `waited_by` is the reverse, among the rows the
board places. `head` and `depth` follow `waits_on` back to a row that waits on none: depth is one
more than the deepest row it waits on, and head is that row's head, the oldest among equals. The
rows of a loop count as one row: each has the loop's depth and head, and a loop that waits on
nothing outside it is depth 1, with its oldest row as head.

`homes` gives each home of each project its row of the stage x home matrix: the root first, then
each scope (`homes.Homes.scopes`), a scope with no open row included, and any other home a row
names, the one with the most open rows first and by name among equals. Each has `open`, how
many rows the board places in it, its `last` act (`state.acts`, the newest whose home it is),
and a cell for each stage a row can be in (`CELLS`):
`count`, the `oldest` row, `old`, how many have a `since` `OLD` or more ago, and `waits`, how
many of its rows wait on each outcome of `checked.OUTCOMES`, as each row's `wait` gives it.

`stuck` is the stage with the most rows not moving, the first in order among equals.
`longest_wait` is the row not moving that came to its stage first. `longest` is the deepest
chain: of the deepest rows, the one that has waited longest, then the one earliest in the
process, and its head. `path` is that chain from its head to that row, each step back the oldest
row it waits on that is one less deep, or a row of its loop, and it stops short of the head
where neither is left. `chains` counts the heads that another row
waits back to. `stacked` counts the rows in `stacked` and the rows they merge after, their
parents, with how many parents wait on each outcome of `checked.OUTCOMES`.

`build` gives one project, `stack` every project jbus keeps. The panel is `ALONE`: `/stack.json`
leaves it out, and `/panel/pipeline.json` with no project answers what `stack` gives
(`jbus.view.App._across`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jbus import queue
from jbus.view import cause as causes
from jbus.view import checked
from jbus.view.state import (
    MOVES_FILE,
    PASS_FILE,
    QUEUE_FILE,
    STEP,
    UNKNOWN,
    WAITING_FILE,
    WORK_FILE,
    Read,
    iso,
    request,
    text,
)

FIRST = False
ALONE = True
STAGES = (
    ("scout", "Scout"),
    ("queued", "Queued"),
    ("crew", "Crew"),
    ("you", "Needs you"),
    ("review", "Review"),
    ("fix", "Fix"),
    ("review2", "Review 2"),
    ("check", "Check"),
    ("stacked", "Stacked"),
    ("merge", "Merge"),
    ("merged", "Merged"),
)
STAGE_OF_STEP = {
    "queued": "queued",
    "running": "crew",
    "gate": "crew",
    "hold": "merge",
    "result": "review",
    "review": "review",
    "findings": "fix",
    "second": "review2",
    "check": "check",
    "proof": "merge",
    "rebase": "merge",
    "merged": "merged",
}
RUNNING_BY_WHO = {"rev": "review"}
ROOT_NAME = "root"
LINKS = ("depends", "merge_after")
OLD = timedelta(hours=1)
_ORDER = {key: at for at, (key, _) in enumerate(STAGES)}
if missed := set(STEP) - {UNKNOWN.key} - set(STAGE_OF_STEP):
    raise ValueError(f"no stage for the steps {sorted(missed)}: add each to STAGE_OF_STEP")
if wrong := {*STAGE_OF_STEP.values(), *RUNNING_BY_WHO.values()} - set(_ORDER):
    raise ValueError(f"{sorted(wrong)} are no stage of STAGES")

_AT = {"slug": None, "project": None, "since": None}
CELLS = tuple(key for key, _ in STAGES if key != "merged")
CELL = {"count": None, "oldest": _AT, "old": None, "waits": checked.SHAPE}
BOARD = {
    "at": None,
    "stages": [
        {"key": None, "name": None, "count": None, "still": None, "oldest": _AT},
    ],
    "rows": [
        {
            "slug": None,
            "project": None,
            "home": None,
            "stage": None,
            "since": None,
            "cause": None,
            "cause_kind": None,
            "cause_since": None,
            "moving": None,
            "waits_on": [{"slug": None, "project": None, "kind": None}],
            "waited_by": [None],
            "head": None,
            "depth": None,
            "wait": None,
        }
    ],
    "unplaced": [{"slug": None, "project": None, "cause": None}],
    "stuck": {"stage": None, "still": None, "count": None},
    "longest_wait": {"slug": None, "project": None, "stage": None, "since": None, "cause": None},
    "longest": {
        "depth": None,
        "head": None,
        "head_project": None,
        "head_stage": None,
        "head_cause": None,
        "chains": None,
        "path": [None],
    },
    "homes": [
        {
            "project": None,
            "name": None,
            "open": None,
            "last": {"at": None, "what": None},
            "cells": dict.fromkeys(CELLS, CELL),
        }
    ],
    "stacked": {"rows": None, "parents": None, "waits": checked.SHAPE},
}
SHAPE = BOARD


SOURCES = (
    PASS_FILE,
    WORK_FILE,
    QUEUE_FILE,
    MOVES_FILE,
    WAITING_FILE,
)


@dataclass(frozen=True)
class Card:
    """One open row of one project: where it is, since when, why, and the rows it waits on."""

    slug: str
    project: str
    home: str
    stage: str | None
    since: str | None
    cause: causes.Cause
    kind: str
    waits_on: tuple[tuple[str, str], ...] = ()
    wait: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.project, self.slug


def _older(card: Card) -> tuple[bool, str]:
    """The sort key of the one that came first, with no time last."""
    return card.since is None, card.since or ""


def _needs(read: Read) -> frozenset[str]:
    """The slug of each need of the You panel."""
    return frozenset(one["slug"] for one in read.panel("you")["needs"] if one["slug"])


def _stage(task: dict[str, Any], needs: frozenset[str]) -> str | None:
    if task["slug"] in needs:
        return "you"
    if task["step"] == "running":
        return RUNNING_BY_WHO.get(task["who"], STAGE_OF_STEP["running"])
    if task["step"] == checked.STEP and checked.outcome(task) == checked.STACKED:
        return "stacked"
    return STAGE_OF_STEP.get(task["step"])


def cards(read: Read) -> list[Card]:
    """Every open row of the project as a card: each task and each scout out."""
    needs = read.once(_needs)
    rows = {row["slug"]: row for row in read.rows}
    tasks = {task["slug"] for task in read.tasks}
    made = []
    for task in read.tasks:
        said = causes.cause(task, read.now)
        row = rows.get(task["slug"], {})
        links = tuple((one, kind) for kind in LINKS for one in row.get(kind) or [] if one in tasks)
        stage = _stage(task, needs)
        kind = (task.get("state") or {}).get("kind") or UNKNOWN.key
        if _researching(read, row) and stage != "you":
            said = causes.Cause("scout researching, no Report yet", task["since"], True)
            stage, kind = "scout", "scout"
        made.append(
            Card(
                task["slug"],
                read.name,
                task["home"] or ROOT_NAME,
                stage,
                task["since"],
                said,
                kind,
                links,
                checked.outcome(task) if task["step"] == checked.STEP else None,
            )
        )
    return made


def _researching(read: Read, row: dict[str, Any]) -> bool:
    """Whether a row is a scout's that launched and whose request has no Report yet."""
    if queue.role(row) != queue.SCOUT or not row.get("thread"):
        return False
    return request(read.home, row["slug"])["state"] == "researching"


def _chains(every: list[Card]) -> dict[tuple[str, str], tuple[int, tuple[str, str]]]:
    """The depth of each card and the key of its head. The cards of a loop count as one card,
    found by Tarjan's walk of the links: each has the depth and head the loop has."""
    by = {card.key: card for card in every}
    ups = {key: [(card.project, slug) for slug, _ in card.waits_on] for key, card in by.items()}
    loop: dict[tuple[str, str], int] = {}
    low: dict[tuple[str, str], int] = {}
    held: list[tuple[str, str]] = []
    loops: list[list[tuple[str, str]]] = []

    def tie(key: tuple[str, str]) -> None:
        loop[key] = low[key] = len(loop)
        held.append(key)
        for up in ups[key]:
            if up not in loop:
                tie(up)
                low[key] = min(low[key], low[up])
            elif up in held:
                low[key] = min(low[key], loop[up])
        if low[key] == loop[key]:
            one = held[held.index(key) :]
            del held[held.index(key) :]
            loops.append(one)

    for key in by:
        if key not in loop:
            tie(key)
    found: dict[tuple[str, str], tuple[int, tuple[str, str]]] = {}
    for one in loops:
        inside = set(one)
        out = [found[up] for key in one for up in ups[key] if up not in inside]
        if out:
            depth, head = min(out, key=lambda up: (-up[0], _older(by[up[1]])))
            made = (depth + 1, head)
        else:
            made = (1, min(one, key=lambda key: (_older(by[key]), key)))
        for key in one:
            found[key] = made
    return found


def _at(card: Card | None) -> dict[str, Any] | None:
    return card and {"slug": card.slug, "project": card.project, "since": card.since}


def _old(card: Card, now: datetime) -> bool:
    """Whether the card's `since` is `OLD` or more before `now`."""
    return card.since is not None and datetime.fromisoformat(card.since) <= now - OLD


def _cell(mine: list[Card], now: datetime) -> dict[str, Any]:
    waits = [card.wait for card in mine]
    return {
        "count": len(mine),
        "oldest": _at(min(mine, key=_older, default=None)),
        "old": sum(1 for card in mine if _old(card, now)),
        "waits": {one: waits.count(one) for one in checked.OUTCOMES},
    }


def _homes(read: Read, placed: list[Card], now: datetime) -> list[dict[str, Any]]:
    """The project's row of the matrix for each of its homes, in the order `homes` names."""
    mine = [card for card in placed if card.project == read.name]
    scopes = [one.name for one, _, _ in read.homes.scopes]
    names = {ROOT_NAME, *scopes, *(card.home for card in mine)} - {ROOT_NAME}
    count = {name: sum(1 for card in mine if card.home == name) for name in names}
    names = [ROOT_NAME, *sorted(names, key=lambda name: (-count[name], name))]
    last = {one["home"] or ROOT_NAME: one for one in read.acts if one["home"] is not None}
    found = []
    for name in names:
        rows = [card for card in mine if card.home == name]
        act = last.get(name)
        found.append(
            {
                "project": read.name,
                "name": name,
                "open": len(rows),
                "last": act and {"at": act["at"], "what": act["what"]},
                "cells": {
                    key: _cell([card for card in rows if card.stage == key], now) for key in CELLS
                },
            }
        )
    return found


def _path(chains: dict[tuple[str, str], tuple[int, tuple[str, str]]], by, tail: Card) -> list[str]:
    """The chain from its head to `tail`: each step back is the oldest row it waits on that is
    one less deep with the same head, or, inside a loop, a row of the loop not yet taken."""
    head = chains[tail.key][1]
    path, at, seen = [tail], tail, {tail.key}
    while at.key != head:
        depth = chains[at.key][0]
        ups = [by[(at.project, slug)] for slug, _ in at.waits_on]
        ups = [up for up in ups if up.key not in seen and chains[up.key][1] == head]
        ups = [up for up in ups if chains[up.key][0] == depth - 1] or [
            up for up in ups if chains[up.key][0] == depth
        ]
        if not ups:
            break
        at = min(ups, key=lambda up: (_older(up), up.key))
        seen.add(at.key)
        path.append(at)
    return [card.slug for card in reversed(path)]


def _stacked(placed: list[Card], by: dict[tuple[str, str], Card]) -> dict[str, Any]:
    """The rows in `stacked`, their parents, and what the parents wait on."""
    rows = [card for card in placed if card.stage == "stacked"]
    parents = {
        (card.project, slug)
        for card in rows
        for slug, kind in card.waits_on
        if kind == "merge_after"
    }
    waits = [by[key].wait for key in parents if key in by]
    return {
        "rows": len(rows),
        "parents": len(parents),
        "waits": {one: waits.count(one) for one in checked.OUTCOMES},
    }


def board(reads: list[Read], now: Any) -> dict[str, Any]:
    """The board of every project of `reads` at `now`."""
    every = [card for read in reads for card in read.once(cards)]
    by = {card.key: card for card in every}
    placed = [card for card in every if card.stage is not None and card.stage != "merged"]
    chains = _chains(every)
    waited: dict[tuple[str, str], list[str]] = {}
    for card in placed:
        for slug, _ in card.waits_on:
            waited.setdefault((card.project, slug), []).append(card.slug)
    placed.sort(key=lambda card: (_ORDER[card.stage], _older(card), card.project, card.slug))
    merged = sum(len(read.panel("merged")["merged"]) for read in reads)
    needs = sum(len(read.panel("you")["needs"]) for read in reads)
    stages = []
    for key, name in STAGES:
        mine = [card for card in placed if card.stage == key]
        still = sum(1 for card in mine if not card.cause.moving)
        oldest = min(mine, key=_older, default=None)
        count = {"merged": merged, "you": needs}.get(key, len(mine))
        stages.append(
            {"key": key, "name": name, "count": count, "still": still, "oldest": _at(oldest)}
        )
    most = max(stages, key=lambda one: one["still"])
    stuck = {"stage": most["key"], "still": most["still"], "count": most["count"]}
    if not most["still"]:
        stuck = {"stage": None, "still": 0, "count": 0}
    waits = [card for card in placed if not card.cause.moving and card.since]
    first = min(waits, key=_older, default=None)
    deepest = min(
        placed,
        key=lambda card: (-chains[card.key][0], _older(card), _ORDER[card.stage], card.key),
        default=None,
    )
    longest = None
    if deepest is not None:
        depth, head = chains[deepest.key]
        top = by[head]
        heads = {chains[card.key][1] for card in placed if chains[card.key][0] > 1}
        longest = {
            "depth": depth,
            "head": top.slug,
            "head_project": top.project,
            "head_stage": top.stage,
            "head_cause": top.cause.text,
            "chains": len(heads),
            "path": _path(chains, by, deepest),
        }
    return {
        "at": iso(now),
        "stages": stages,
        "rows": [
            {
                "slug": card.slug,
                "project": card.project,
                "home": card.home,
                "stage": card.stage,
                "since": card.since,
                "cause": text(card.cause.text, 300),
                "cause_kind": card.kind,
                "cause_since": card.cause.since,
                "moving": card.cause.moving,
                "waits_on": [
                    {"slug": slug, "project": card.project, "kind": kind}
                    for slug, kind in card.waits_on
                ],
                "waited_by": sorted(waited.get(card.key, [])),
                "head": by[chains[card.key][1]].slug,
                "depth": chains[card.key][0],
                "wait": card.wait,
            }
            for card in placed
        ],
        "unplaced": [
            {"slug": card.slug, "project": card.project, "cause": text(card.cause.text, 300)}
            for card in every
            if card.stage is None
        ],
        "stuck": stuck,
        "longest_wait": first
        and {
            "slug": first.slug,
            "project": first.project,
            "stage": first.stage,
            "since": first.since,
            "cause": text(first.cause.text, 300),
        },
        "longest": longest,
        "homes": [one for read in reads for one in _homes(read, placed, now)],
        "stacked": _stacked(placed, by),
    }


def build(read: Read) -> dict[str, Any]:
    return board([read], read.now)


def stack(base: Read, reads: list[Read], answer: dict[str, Any]) -> dict[str, Any]:
    return board(reads, base.now)
