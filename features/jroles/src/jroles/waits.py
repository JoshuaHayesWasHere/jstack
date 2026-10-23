"""The threads that wait for a capped pool to reset, in one file beside the ledger.

A crew that finds every instance of the review pool capped makes no launch and ends its turn.
Nothing in T3 Code wakes it when the cap lifts, so it registers here first, through
`jroles review --thread <id>`, with the time `jroles.pool` gives for the first reset. Each pass
of `jbus poll` reads this file, and once that time has passed it sends the thread one message
(`jbus.slotwait.wake_capped`). This module handles the file and nothing else: it knows nothing
of T3 Code. It is shaped like `jgauge.waiters`, the file of the threads that wait on a test slot,
and is a file of its own because a thread may wait on a slot and on the pool at once.

`pool-waiters.json` is a list of `Wait`, beside the ledger's files (`ledger.path`), so it
belongs to the machine and not to a project. Each change takes the lock `pool-waiters.lock` and
replaces the whole file with a rename, so a reader never sees half a list. A wait is:

- `thread` and `role` say who waits on which pool;
- `until` is when the pool's first instance resets, as `jroles.pool.Choice.until` gives it;
- `since` is when the thread first waited;
- `id` names this wait, and keys its wake, so a retry of the wake is still one message.

Registering is idempotent: a thread that registers again for a role it still waits on keeps its
wait and its id, with the newer `until`. A thread that finds headroom leaves the file (`drop`),
and so does a wait that jbus woke (`forget`), so the thread's next wait gets a message of its own.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from jroles import ledger

NAME = "pool-waiters.json"
LOCK = "pool-waiters.lock"
PREFIX = "mcp:"


@dataclass(frozen=True)
class Wait:
    thread: str
    role: str
    until: str
    since: str
    id: str

    def due(self, now: datetime) -> bool:
        """Whether the pool's cap has ended, so the thread can launch again."""
        return now >= datetime.fromisoformat(self.until)


def where() -> Path:
    return ledger.path().parent


def thread_id(text: str) -> str:
    """The thread's id in T3 Code's form: the prefix `mcp:`, then the id."""
    return text if not text or text.startswith(PREFIX) else PREFIX + text


@contextmanager
def _held(at: Path) -> Iterator[None]:
    at.mkdir(parents=True, exist_ok=True)
    fd = os.open(at / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _read(at: Path) -> list[Wait]:
    try:
        return [Wait(**one) for one in json.loads((at / NAME).read_text())]
    except (OSError, ValueError, TypeError):
        return []


def _change(at: Path, how: Callable[[list[Wait]], list[Wait]]) -> None:
    with _held(at):
        was = _read(at)
        now = how(was)
        if now != was:
            temp = at / f".{NAME}.{os.getpid()}"
            temp.write_text(json.dumps([asdict(one) for one in now], indent=2) + "\n")
            os.replace(temp, at / NAME)


def read(at: Path) -> list[Wait]:
    """Every wait, the oldest first."""
    with _held(at):
        return sorted(_read(at), key=lambda one: (one.since, one.id))


def register(at: Path, thread: str, role: str, until: datetime, now: datetime) -> Wait:
    """Make `thread` a waiter on the pool of `role` until `until`, and return its wait."""
    made: list[Wait] = []
    thread = thread_id(thread)

    def how(waits: list[Wait]) -> list[Wait]:
        mine = next((one for one in waits if (one.thread, one.role) == (thread, role)), None)
        others = [one for one in waits if one is not mine]
        moment = until.astimezone(UTC).isoformat()
        if mine:
            wait = replace(mine, until=moment)
        else:
            since = now.astimezone(UTC).isoformat(timespec="seconds")
            wait = Wait(thread, role, moment, since, secrets.token_hex(6))
        made.append(wait)
        return [*others, wait]

    _change(at, how)
    return made[0]


def drop(at: Path, thread: str, role: str) -> None:
    """Take the thread's wait on `role` out, since the pool has headroom for it. When there is no
    file, the function does nothing and creates no file."""
    if not (at / NAME).exists():
        return
    thread = thread_id(thread)
    _change(at, lambda waits: [one for one in waits if (one.thread, one.role) != (thread, role)])


def forget(at: Path, ids: set[str]) -> None:
    """Take out the waits with these ids: jbus woke them, or their threads are gone."""
    _change(at, lambda waits: [one for one in waits if one.id not in ids])
