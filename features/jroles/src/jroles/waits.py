"""The threads that wait for a capped pool to reset, in one file beside the ledger.

A crew that finds every instance of the review pool capped makes no launch and ends its turn.
Nothing in T3 Code wakes it when the cap lifts, so it registers here first, through
`jroles review --thread <id>`, with the time `jroles.pool` gives for the first reset. Each pass
of `jbus poll` reads this file, and once that time has passed it sends the thread one message
(`jbus.slotwait.wake_capped`). This module handles the file and nothing else: it knows nothing
of T3 Code. It is a `jsettings.LockedList`, as `jgauge.waiters`, the file of the threads that
wait on a test slot, is, and is a file of its own because a thread may wait on a slot and on
the pool at once.

`pool-waiters.json` is a list of `Wait`, beside the ledger's files (`ledger.path`), so it
belongs to the machine and not to a project. Each change takes the lock `pool-waiters.lock` and
replaces the whole file with a rename, so a reader never sees half a list. A wait is:

- `thread` and `role` say who waits on which pool;
- `until` is when the pool's first instance resets, as `jroles.pool.Choice.until` gives it;
- `since` is when the thread first waited;
- `id` names this wait, and keys its wake, so a retry of the wake is still one message.

Registering is idempotent: a thread that registers again for a role it still waits on keeps its
wait and its id, with the newer `until`. A wait that is due already is the one jbus woke or is
waking, so a thread that registers then gets a new wait, with an id of its own. A thread that finds
headroom leaves the file (`drop`), and so does a wait that jbus woke (`forget`), so the thread's
next wait gets a message of its own.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import jsettings
from jroles import ledger
from jsettings import thread_id

NAME = "pool-waiters.json"
LOCK = "pool-waiters.lock"


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


FILE = jsettings.LockedList(NAME, LOCK, lambda raw: [Wait(**one) for one in raw])


def where() -> Path:
    return ledger.path().parent


def read(at: Path) -> list[Wait]:
    """Every wait, the oldest first."""
    return FILE.read(at)


def register(at: Path, thread: str, role: str, until: datetime, now: datetime) -> Wait:
    """Make `thread` a waiter on the pool of `role` until `until`, and return its wait."""
    made: list[Wait] = []
    thread = thread_id(thread)

    def how(waits: list[Wait]) -> list[Wait]:
        mine = next((one for one in waits if (one.thread, one.role) == (thread, role)), None)
        others = [one for one in waits if one is not mine]
        moment = until.astimezone(UTC).isoformat()
        if mine and not mine.due(now):
            wait = replace(mine, until=moment)
        else:
            since = jsettings.stamp(now)
            wait = Wait(thread, role, moment, since, secrets.token_hex(6))
        made.append(wait)
        return [*others, wait]

    FILE.change(at, how)
    return made[0]


def drop(at: Path, thread: str, role: str) -> None:
    """Take the thread's wait on `role` out, since the pool has headroom for it. When there is no
    file, the function does nothing and creates no file."""
    if not FILE.there(at):
        return
    thread = thread_id(thread)
    FILE.change(
        at, lambda waits: [one for one in waits if (one.thread, one.role) != (thread, role)]
    )


def forget(at: Path, ids: set[str]) -> None:
    """Take out the waits with these ids: jbus woke them, or their threads are gone."""
    FILE.change(at, lambda waits: [one for one in waits if one.id not in ids])
