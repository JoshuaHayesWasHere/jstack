"""The threads that wait on a test slot. The module keeps them in one file, the slot queue's.

A thread that finds every slot of a lane taken does not poll and does not end its turn
silent. It registers here, through `jgauge test-slot --thread <id>`, and ends its turn with
one line. `jbus poll` reads this file, and when a lane has a slot free it sends the oldest
waiter on that lane one message (`jbus.slotwait`). This module handles the file and nothing
else: it knows nothing of T3 Code, and jbus calls it for every change.

`test-slot-waiters.json` is beside the slots' lock files and is a list of `Waiter`. Each
change takes the lock `test-slot-waiters.lock` and replaces the whole file with a rename, so a
reader never sees half a list. A waiter is one wait:

- `thread`, `lane` and `slots` say who waits on what: `lane` is `short` or `full`, and `slots`
  is how many slots the lane has;
- `command` is what the thread will run, for the message that wakes it;
- `since` is when the thread first waited, and orders the queue. A thread that jbus wakes and
  that finds the slot taken again keeps waiting from the same `since`, so it does not go to the
  back;
- `id` names this wait, so a retry of its wake is one message and the next wait is another;
- `woken` is when jbus sent the wake, or nothing. jbus wakes a wait once.

Registering is idempotent: a thread that registers again for a wait it still has, on the same
lane and not yet woken, changes nothing but the command it will run. A thread that takes a slot
leaves the file (`drop`).

A thread has one form of id, T3 Code's `mcp:<uuid>`, and `thread_id` adds the prefix to an id
given without it. A file written before this rule may hold two records for one thread. They
count as one wait that keeps the older record's place. The module keeps the older record.
Where jbus woke the older record and not the later one, it keeps the later record instead, with
the older `since`. The next change writes the file in that form.
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
    kept: dict[str, Waiter] = {}
    for one in sorted(read, key=lambda one: (one.since, one.id)):
        older = kept.get(one.thread)
        if older is None:
            kept[one.thread] = one
        elif older.woken and not one.woken:
            kept[one.thread] = replace(one, since=older.since)
    return list(kept.values())


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
    """Make `thread` a waiter on `lane`, and return its wait. A thread that already waits
    there, not yet woken, keeps its wait and its place. A thread that jbus woke and that
    registers again keeps its place in the queue and has a new wait."""
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
    out of, and the function makes none."""
    if not (locks / NAME).exists():
        return
    thread = thread_id(thread)
    _change(locks, lambda waiters: [one for one in waiters if one.thread != thread])


def forget(locks: Path, ids: set[str]) -> None:
    """Take out the waits with these ids. A thread that waits again has another id, and stays."""
    _change(locks, lambda waiters: [one for one in waiters if one.id not in ids])


def woken(locks: Path, wait: str, now: datetime) -> None:
    """Record that jbus sent the wait with this id its wake."""
    _change(
        locks,
        lambda waiters: [
            replace(one, woken=stamp(now)) if one.id == wait and not one.woken else one
            for one in waiters
        ],
    )


def holding(waiter: Waiter, now: datetime) -> bool:
    """Whether a woken wait still has the slot that jbus woke it for: jbus woke it `HOLDS` ago
    or less, and its thread has not taken the slot yet."""
    return bool(waiter.woken) and now - _when(waiter.woken) <= HOLDS


def lapsed(waiter: Waiter, now: datetime) -> bool:
    """Whether a woken wait is long past: jbus woke its thread over `FORGOTTEN` ago, and the
    thread has not taken the slot."""
    return bool(waiter.woken) and now - _when(waiter.woken) > FORGOTTEN
