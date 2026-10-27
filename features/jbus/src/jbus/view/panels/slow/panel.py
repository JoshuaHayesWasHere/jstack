"""What slows the work: for each stage a row can wait at, how many rows wait there and the one
that has waited longest, and how many of the machine's test slots are held.

A stage is a row of `STAGES`. Three take the tasks of the line by their step or their holder:
`runner` is the step `check`, where a row waits for a runner and then for its check to end;
`review` is every step a reviewer holds; `rebase` is the step `rebase`. The fourth, `you`, is
what Needs you lists, so its count is the one the page's Needs you gives. A task's age at its
stage is its `since`, which the line gives (`state._tasks`). Of a row in check, `running` counts
the ones whose check has started and not ended: the rest wait for a runner.

The test slots are the full lane of `jgauge test-slot` (`jgauge.slot`), where a thread runs the
check command. The panel never takes a slot's lock to see whether it is free, as
`jgauge.slot.free` does: a real `take` at that moment would find the slot taken. It reads the
kernel's list of held locks, `<proc>/locks`, and counts the lock files of the lane that are in
it. The threads that wait for a slot are the full lane's waiters (`jgauge.waiters`).

The overview of every project gives the stages across the projects (`stack`), and the panel of
one project gives them for that project (`build`). The machine's load is the room's, which the
page already has: this panel does not give it again.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jbus.view.state import Read, Source, iso
from jgauge import slot, waiters

FIRST = False
_OLDEST = {"what": None, "project": None, "since": None, "open": None}
SHAPE = {
    "slow": {
        "stages": [{"key": None, "name": None, "rows": None, "running": None, "oldest": _OLDEST}],
        "slots": {"read": None, "used": None, "total": None, "waiting": None, "since": None},
    }
}
LANE = "full"


@dataclass(frozen=True)
class Stage:
    """One stage a row waits at: its key, its name on the page, and which tasks wait there."""

    key: str
    name: str
    holds: Callable[[dict[str, Any]], bool]


STAGES = (
    Stage("runner", "a runner", lambda task: task["step"] == "check"),
    Stage("review", "review", lambda task: task["who"] == "rev"),
    Stage("rebase", "a rebase", lambda task: task["step"] == "rebase"),
)
YOU = "you"


def _running(task: dict[str, Any]) -> bool:
    check = task["seen"]["check"] or {}
    return bool(check.get("started")) and not check.get("completed")


def _first(found: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one that has waited longest: the oldest `since`, and one with no time last."""
    ordered = sorted(found, key=lambda one: (one["since"] is None, one["since"] or ""))
    return ordered[0] if ordered else None


def stages(reads: list[Read], needs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each stage, with the rows of every project of `reads` that wait there."""
    found = []
    for stage in STAGES:
        mine = [(read.name, task) for read in reads for task in read.tasks if stage.holds(task)]
        oldest = _first(
            [
                {
                    "what": task["slug"],
                    "project": name,
                    "since": task["since"],
                    "open": f"#/{quote(name, safe='')}/task/{quote(task['slug'], safe='')}",
                }
                for name, task in mine
            ]
        )
        running = sum(1 for _, task in mine if _running(task)) if stage.key == "runner" else None
        found.append(
            {
                "key": stage.key,
                "name": stage.name,
                "rows": len(mine),
                "running": running,
                "oldest": oldest,
            }
        )
    oldest = _first([{key: one[key] for key in _OLDEST} for one in needs])
    return [
        *found,
        {"key": YOU, "name": YOU, "rows": len(needs), "running": None, "oldest": oldest},
    ]


def used(proc: Path, locks: Path, total: int) -> int | None:
    """How many of the lane's `total` lock files the kernel lists as held, or None where its
    list of locks cannot be read. A lock is the device and the inode of its file, as
    `<proc>/locks` gives them, and a line with `->` is a process that waits for the lock."""
    try:
        listed = (proc / "locks").read_text().splitlines()
    except OSError:
        return None
    held = {words[5] for words in map(str.split, listed) if len(words) > 5 and words[1] != "->"}
    count = 0
    for n in range(1, total + 1):
        try:
            seen = (locks / f"{slot.full(total).lock}.{n}.lock").stat()
        except OSError:
            continue
        count += f"{os.major(seen.st_dev):02x}:{os.minor(seen.st_dev):02x}:{seen.st_ino}" in held
    return count


def slots(read: Read) -> dict[str, Any]:
    """The full lane's slots: how many are held of how many, and the threads that wait for one,
    with the oldest wait. The view reads and never writes, so the waiters come from
    `waiters.FILE.peek`: `waiters.read` takes the file's lock, and makes it."""
    locks = slot.locks_dir()
    try:
        total: int | None = slot.count(None)
    except slot.BadCount:
        total = None
    held = used(read.sources.proc, locks, total) if total else None
    waits = [one for one in waiters.FILE.peek(locks) if one.lane == LANE]
    return {
        "read": held is not None,
        "used": held,
        "total": total,
        "waiting": len(waits),
        "since": min((one.since for one in waits), default=None),
    }


def _slots(read: Read) -> dict[str, Any]:
    return {"at": iso(read.now), "read": read.machine(slots)["read"]}


SOURCES = (Source("test slots", "server", _slots, 165, machine=True),)


def build(read: Read) -> dict[str, Any]:
    needs = read.panel("you")["needs"]
    return {"slow": {"stages": stages([read], needs), "slots": read.machine(slots)}}


def stack(base: Read, reads: list[Read], answer: dict[str, Any]) -> dict[str, Any]:
    return {"slow": {"stages": stages(reads, answer["needs"]), "slots": base.machine(slots)}}
