"""The threads that wait on a test slot: one file, which the slot queue owns.

A thread that finds every slot of a lane taken does not poll and does not end its turn
silent. It registers here, `jgauge test-slot --thread <id>` does that for it, and ends its turn
with one line. `jbus poll` reads this file, and when a lane has a slot free it sends the
oldest waiter on that lane one message (`jbus.slotwait`). This module is the file and nothing
else: it knows no T3 Code, and jbus asks it for every change.

`test-slot-waiters.json` lies beside the slots' lock files and is a list of `Waiter`. Each
change holds `test-slot-waiters.lock` and writes the file whole by a rename, so a reader never
sees half a list. A waiter is one wait:

- `thread`, `lane` and `slots` say who waits on what (`lane` is `short` or `full`, `slots` how
  many the lane has), and `command` what it will run, for the message that wakes it;
- `since` is when the thread first waited, and orders the queue: a thread that is woken and
  finds the slot taken again waits on from the same `since`, so it does not go to the back;
- `id` names this wait, so a retry of its wake is one message and the next wait is another;
- `woken` is when the wake was sent, or nothing. A wait is woken once.

Registering is idempotent: a thread that registers again for a wait it still has, on the same
lane and not yet woken, changes nothing but the command it will run. A thread that takes a slot
leaves the file (`drop`).

A thread is named one way: T3 Code's id is `mcp:<uuid>`, and an id given without the prefix
gets it (`thread_id`). Two records for one thread, as a file written before held, are one wait,
the older, which keeps its place; the file is written so on its next change.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

NAME = "test-slot-waiters.json"
LOCK = "test-slot-waiters.lock"
HOLDS = timedelta(minutes=10)
FORGOTTEN = timedelta(hours=1)
PREFIX = "mcp:"


@dataclass(frozen=True)
class Waiter:
    thread: str
    lane: str
    slots: int
    command: tuple[str, ...]
    since: str
    id: str
    woken: str = ""


def thread_id(text: str) -> str:
    """The thread's id in T3 Code's form, `mcp:` and its id."""
    return text if not text or text.startswith(PREFIX) else PREFIX + text


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@contextmanager
def _held(locks: Path) -> Iterator[None]:
    locks.mkdir(parents=True, exist_ok=True)
    fd = os.open(locks / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _read(locks: Path) -> list[Waiter]:
    try:
        raw = json.loads((locks / NAME).read_text())
        read = [
            Waiter(**{**one, "command": tuple(one["command"]), "thread": thread_id(one["thread"])})
            for one in raw
        ]
    except (OSError, ValueError, TypeError, KeyError):
        return []
    first: dict[str, Waiter] = {}
    for one in sorted(read, key=lambda one: (one.since, one.id)):
        first.setdefault(one.thread, one)
    return [one for one in read if first[one.thread] is one]


def _write(locks: Path, waiters: list[Waiter]) -> None:
    target = locks / NAME
    temp = locks / f".{NAME}.{os.getpid()}"
    temp.write_text(json.dumps([asdict(one) for one in waiters], indent=2) + "\n")
    os.replace(temp, target)


def _change(locks: Path, how: Callable[[list[Waiter]], list[Waiter]]) -> None:
    with _held(locks):
        was = _read(locks)
        now = how(was)
        if now != was:
            _write(locks, now)


def read(locks: Path) -> list[Waiter]:
    """Every waiter, the oldest wait first."""
    with _held(locks):
        return sorted(_read(locks), key=lambda one: (one.since, one.id))


def register(
    locks: Path, thread: str, lane: str, slots: int, command: list[str], now: datetime
) -> Waiter:
    """Make `thread` a waiter on `lane`, and give back its wait. One that already waits there,
    not yet woken, keeps its wait and its place. One that was woken and is back keeps its place
    in the queue and has a new wait."""
    made: list[Waiter] = []
    thread = thread_id(thread)

    def how(waiters: list[Waiter]) -> list[Waiter]:
        mine = next((one for one in waiters if one.thread == thread), None)
        others = [one for one in waiters if one.thread != thread]
        same = mine is not None and (mine.lane, mine.slots) == (lane, slots)
        since = mine.since if same and mine else stamp(now)
        if mine and same and not mine.woken:
            wait = replace(mine, command=tuple(command))
        else:
            wait = Waiter(thread, lane, slots, tuple(command), since, secrets.token_hex(6))
        made.append(wait)
        return [*others, wait]

    _change(locks, how)
    return made[0]


def drop(locks: Path, thread: str) -> None:
    """Take `thread` out: it took its slot. With no waiters file there is nothing to take it
    out of, and none is made."""
    if not (locks / NAME).exists():
        return
    thread = thread_id(thread)
    _change(locks, lambda waiters: [one for one in waiters if one.thread != thread])


def forget(locks: Path, ids: set[str]) -> None:
    """Take out the waits with these ids. A thread that waits again has another id, and stays."""
    _change(locks, lambda waiters: [one for one in waiters if one.id not in ids])


def woken(locks: Path, wait: str, now: datetime) -> None:
    """Record that the wait with this id was sent its wake."""
    _change(
        locks,
        lambda waiters: [
            replace(one, woken=stamp(now)) if one.id == wait and not one.woken else one
            for one in waiters
        ],
    )


def holding(waiter: Waiter, now: datetime) -> bool:
    """Whether a woken wait still has the slot it was woken for: it was woken `HOLDS` ago or
    less, and has not taken it yet."""
    return bool(waiter.woken) and now - _when(waiter.woken) <= HOLDS


def lapsed(waiter: Waiter, now: datetime) -> bool:
    """Whether a woken wait is long past: its thread was told, and nothing came of it."""
    return bool(waiter.woken) and now - _when(waiter.woken) > FORGOTTEN
