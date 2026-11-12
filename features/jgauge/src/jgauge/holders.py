"""The threads whose own command holds a test slot, beside the threads that wait on one
(`jgauge.waiters`).

A thread can end its turn while a run it started still holds a slot. That thread is at work, and
nothing in T3 Code says so: its turn is over, and its status is `completed`. So `jgauge test-slot
--thread <id>` records the run here when its command starts, and records its end when the command
ends, however it ends. `jbus poll` reads this file: a thread with a run that holds a slot is at
work (`jbus.watch.owned_waits`), and once the run has ended jbus wakes the thread once, if it is
not at work by then, with the command and its exit code (`jbus.slotwait.wake_ended`).

`test-slot-holders.json` is beside the slots' lock files and is a list of `Holder`, kept as the
waiters' file is (`jsettings.LockedList`). A holder is one run:

- `thread`, `lane` and `command` say whose run it is and what it runs;
- `pid` is the command's process, and `keeper` the process of the `jgauge test-slot` that holds
  the slot and records the end. A run with no end recorded holds its slot while either lives:
  once the command is gone its `jgauge test-slot` has yet to record the end. A run whose two
  processes are gone with no end recorded, since its `jgauge test-slot` was killed with no chance
  to record it, holds nothing (`running`). A record an older jgauge wrote has no `keeper`, 0, and
  goes by its command alone;
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
from typing import Any

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
    keeper: int = 0


def _fields(one: dict[str, Any]) -> dict[str, Any]:
    return {**one, "command": tuple(one["command"]), "thread": thread_id(one["thread"])}


def _parse(raw: list[dict]) -> list[Holder]:
    return [Holder(**_fields(one)) for one in raw]


FILE = jsettings.LockedList(NAME, LOCK, _parse)


def read(locks: Path) -> list[Holder]:
    """Every run on record, the oldest first."""
    return FILE.read(locks)


def hold(
    locks: Path,
    thread: str,
    lane: str,
    pid: int,
    command: list[str],
    now: datetime,
    keeper: int | None = None,
) -> Holder:
    """Record that `thread`'s command, process `pid`, started under a slot of `lane` that the
    `jgauge test-slot` of process `keeper` holds, this process unless the caller names another."""
    run = Holder(
        thread_id(thread),
        lane,
        pid,
        tuple(command),
        jsettings.stamp(now, z=True),
        secrets.token_hex(6),
        keeper=os.getpid() if keeper is None else keeper,
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
    """Whether the run still holds its slot: its end is not recorded, and its command or the
    `jgauge test-slot` that records the end is there."""
    return not one.ended and (_alive(one.pid) or _alive(one.keeper))


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
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
