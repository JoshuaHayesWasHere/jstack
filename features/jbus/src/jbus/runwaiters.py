"""The threads that wait on a GitHub Actions run they started, in one file of jbus's state.

A crew that proves a change on a run it dispatched, such as the macOS nightly or a browser run,
waits most of an hour for it. Nothing in T3 Code wakes the crew when the run ends, so it
registers here first, through `jbus run-wait <run> --thread <id>` (`jbus.runwait`), and ends its
turn. Each pass of `jbus poll` reads this file for its project, asks GitHub once for each run, and
sends the thread one message once its run has ended. This module handles the file and nothing
else: it knows nothing of T3 Code or GitHub. It is a `jsettings.LockedList`, as
`jgauge.waiters` and `jroles.waits` are.

`run-waiters.json` is a list of `RunWait` in jbus's state directory, so it belongs to the
machine, and each wait names its project. Each change takes the lock `run-waiters.lock` and
replaces the whole file with a rename, so a reader never sees half a list. A wait is:

- `thread` waits on the run `run` of the project `project`;
- `name` and `url` are the run's workflow and its page, as GitHub gave them at the register;
- `since` is when the thread registered;
- `id` names this wait, and keys its wake, so a retry of the wake is still one message.

Registering is idempotent: a thread that registers again for a run it still waits on keeps its
wait and its id. A wait leaves the file once its wake went, or its thread is gone (`forget`).
While it is in the file, its thread's turn ended on a wait that jbus owns (`watch.owned_waits`),
and its row says what it waits on (`waiting`).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jsettings
from jsettings import paths, thread_id

NAME = "run-waiters.json"
LOCK = "run-waiters.lock"


@dataclass(frozen=True)
class RunWait:
    thread: str
    project: str
    run: str
    name: str
    url: str
    since: str
    id: str

    def why(self) -> str:
        """What the thread's row waits on while the run goes."""
        return f"waiting on GitHub run {self.run} ({self.name})"


FILE = jsettings.LockedList(NAME, LOCK, lambda raw: [RunWait(**one) for one in raw])


def where() -> Path:
    at = paths.jbus_state_dir()
    at.mkdir(parents=True, exist_ok=True)
    return at


def read(at: Path) -> list[RunWait]:
    """Every wait, the oldest first."""
    return FILE.read(at)


def register(
    at: Path, thread: str, project: str, run: str, name: str, url: str, now: datetime
) -> RunWait:
    """Make `thread` wait on the run `run` of `project`, and return its wait. A thread that
    already waits on that run keeps its wait."""
    made: list[RunWait] = []
    thread = thread_id(thread)

    def how(held: list[RunWait]) -> list[RunWait]:
        for one in held:
            if (one.thread, one.project, one.run) == (thread, project, run):
                made.append(one)
                return held
        wait = RunWait(thread, project, run, name, url, now.isoformat(), secrets.token_hex(6))
        made.append(wait)
        return [*held, wait]

    FILE.change(at, how)
    return made[0]


def forget(at: Path, ids: set[str]) -> None:
    """Take the waits `ids` out of the file: each was woken, or its thread is gone."""
    FILE.change(at, lambda held: [one for one in held if one.id not in ids])


def waiting(at: Path) -> dict[str, str]:
    """What each thread that waits on a run waits on, by the thread: the reason its row gives,
    with every run it waits on."""
    found: dict[str, list[str]] = {}
    for one in FILE.peek(at):
        found.setdefault(one.thread, []).append(one.why())
    return {thread: "; ".join(whys) for thread, whys in found.items()}
