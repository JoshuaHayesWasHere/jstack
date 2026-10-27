"""The threads whose own command holds a test slot, beside the threads that wait on one
(`jgauge.waiters`).

A thread can end its turn while a run it started still holds a slot. That thread is at work, and
nothing in T3 Code says so: its turn is over, and its status is `completed`. So `jgauge test-slot
--thread <id>` records the run here when its command starts, and records its end when the command
ends, however it ends. `jbus poll` reads this file: a thread with a run that holds a slot is at
work (`jbus.watch.World.holding`), and once the run has ended jbus wakes the thread once, if it is
not at work by then, with the command and its exit code (`jbus.slotwait.wake_ended`).

`test-slot-holders.json` is beside the slots' lock files and is a list of `Holder`, kept as the
waiters' file is (`jsettings.LockedList`). A holder is one run:

- `thread`, `lane` and `command` say whose run it is and what it runs;
- `pid` is the command's process. A run whose process is gone and whose end is not recorded,
  since the holder was killed with no chance to record it, holds nothing (`running`);
- `since` is when the command started, and `id` names the run;
- `ended` is when the command ended, or nothing while it runs, and `code` its exit code.

An ended run stays in the file until jbus has woken its thread or found that it needs no wake.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import jsettings
from jsettings import thread_id

NAME = "test-slot-holders.json"
LOCK = "test-slot-holders.lock"


@dataclass(frozen=True)
class Holder:
    thread: str
    lane: str
    pid: int
    command: tuple[str, ...]
    since: str
    id: str
    ended: str = ""
    code: int | None = None


def _parse(raw: list[dict]) -> list[Holder]:
    return [
        Holder(**{**one, "command": tuple(one["command"]), "thread": thread_id(one["thread"])})
        for one in raw
    ]


FILE = jsettings.LockedList(NAME, LOCK, _parse)


def read(locks: Path) -> list[Holder]:
    """Every run on record, the oldest first."""
    return FILE.read(locks)


def hold(
    locks: Path, thread: str, lane: str, pid: int, command: list[str], now: datetime
) -> Holder:
    """Record that `thread`'s command, process `pid`, started under a slot of `lane`."""
    run = Holder(
        thread_id(thread),
        lane,
        pid,
        tuple(command),
        jsettings.stamp(now, z=True),
        secrets.token_hex(6),
    )
    FILE.change(locks, lambda held: [*held, run])
    return run


def end(locks: Path, run: str, code: int, now: datetime) -> None:
    """Record that the run with this id ended with `code`."""
    FILE.change(
        locks,
        lambda held: [
            replace(one, ended=jsettings.stamp(now, z=True), code=code)
            if one.id == run and not one.ended
            else one
            for one in held
        ],
    )


def forget(locks: Path, ids: set[str]) -> None:
    """Take out the runs with these ids."""
    FILE.change(locks, lambda held: [one for one in held if one.id not in ids])


def running(one: Holder) -> bool:
    """Whether the run still holds its slot: its end is not recorded and its process is there."""
    if one.ended:
        return False
    try:
        os.kill(one.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def holding(locks: Path) -> list[Holder]:
    """The runs that hold a slot now (`running`). When there is no holders file, the function
    finds none and creates no file."""
    if not FILE.there(locks):
        return []
    return [one for one in read(locks) if running(one)]
