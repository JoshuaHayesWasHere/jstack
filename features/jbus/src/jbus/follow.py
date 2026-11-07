"""`jbus follow`: restate a thread's line of `work.json` within milliseconds of T3 Code's event.

T3 Code pushes its orchestration events to its own app over `/ws`, and refuses jbus's sign-in
there: it takes an MCP client's token at `/mcp` alone, and `/mcp` pushes nothing. So jbus follows
the same events where T3 Code keeps them, the table `orchestration_events` of its store,
`$T3CODE_HOME/userdata/statev2.sqlite` (`jbus.boxes.store`), read only, as `jbus.boxes` reads it.
A write of the store wakes the follower (inotify on the store's folder, on Linux; elsewhere, and
at the latest, every `TICK` seconds), and it reads the events after the last one it read, again
for a few milliseconds where the write's commit is not published yet (`SETTLE`).

Four kinds of event move a thread (`facet`): a run that runs, waits, or ended, a thread settled,
and a thread archived. The follower takes the last of them for each thread, and restates the
`Thread` facet of each line of each project's `work.json` that names that thread
(`restated.followed`), under `work.LOCK`. A run being prepared, queued or started moves nothing: it
runs within milliseconds, or it waits behind a run under way.

The follower's stream is lost when the store cannot be read, is no longer the file it opened, or
starts its events over. It then opens the store again, `BACKOFF` seconds apart at most, and reads
on from the store's last event: what happened between is the pass's to correct, and the pass logs
each line it corrects as drift (`work.drift`). So the follower never replays an old event over a
line a pass judged since, and a follower started twice, or again after a crash, ends where one
would. `restated.FOLLOW` in jbus's state directory says since when it follows and how often it
lost its stream; the pass reads a thread's facet as drift only while that record is there
(`restated.following`).
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import os
import select
import sqlite3
import struct
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jbus import Config, boxes, restated, verbs, work, write_json

TICK = 1.0
"""The longest the follower sleeps with no write of the store seen."""
BACKOFF = 5.0
"""The longest the follower waits between two tries to open a lost store."""
SETTLE = (0.002, 0.005, 0.01, 0.02, 0.05, 0.1)
"""The pauses between reads after a write woke the follower and no new event showed yet. SQLite
writes a transaction into the store's `-wal` file, which wakes the follower, before it publishes
the commit in the `-shm` index, which wakes nothing: a read at once can come before the commit."""
KINDS = ("run.created", "run.updated", "thread.settled", "thread.archived")
_TAIL = f"""
select sequence, stream_id, event_type, occurred_at, json_extract(payload_json, '$.status')
from orchestration_events
where sequence > ? and aggregate_kind = 'thread'
and event_type in ({", ".join("?" for _ in KINDS)})
order by sequence
"""
_LAST = "select coalesce(max(sequence), 0) from orchestration_events"
_RUNS = {
    "running": work.Thread.MOVING,
    "waiting": work.Thread.WAITING,
    "completed": work.Thread.COMPLETED,
    "idle": work.Thread.COMPLETED,
    **dict.fromkeys(("failed", "interrupted", "cancelled", "rolled_back"), work.Thread.FAILED),
}


class Lost(Exception):
    """The follower's stream is lost: the store cannot be read, or is not the one it opened."""


@dataclass(frozen=True)
class Event:
    """One event of T3 Code's store that moves a thread: its sequence, its thread, the facet it
    gives that thread, and when it happened, as `restated.moment` writes it."""

    sequence: int
    thread: str
    facet: work.Thread
    at: str


def facet(kind: str, status: str | None) -> work.Thread | None:
    """Return the `Thread` facet an event gives its thread, or None for one that moves it
    nowhere the pass would not judge alike: a run being prepared, queued or started."""
    if kind == "thread.settled":
        return work.Thread.SETTLED
    if kind == "thread.archived":
        return work.Thread.ARCHIVED
    return _RUNS.get(status or "")


def moment(occurred: str) -> str:
    """Return T3 Code's `occurred_at` as `restated.moment` writes a time, so stamps compare as
    text."""
    at = datetime.fromisoformat(occurred)
    return restated.moment(at if at.tzinfo else at.replace(tzinfo=UTC))


class Store:
    """T3 Code's store, open read only, and the sequence of the last event read."""

    def __init__(self, where: Path) -> None:
        self.where = where
        try:
            self.inode = where.stat().st_ino
            self.db = sqlite3.connect(f"file:{where}?mode=ro", uri=True, timeout=1)
            self.sequence = int(self.db.execute(_LAST).fetchone()[0])
        except (OSError, sqlite3.Error) as error:
            raise Lost(f"T3 Code's store at {where} cannot be read ({error})") from None
        self.moved = False

    def read(self) -> list[Event]:
        """Return the events after the last one read that move a thread, oldest first, and say in
        `moved` whether the store had any event after the last one read, of any kind."""
        try:
            if self.where.stat().st_ino != self.inode:
                raise Lost(f"T3 Code's store at {self.where} is another file now")
            rows = self.db.execute(_TAIL, (self.sequence, *KINDS)).fetchall()
            last = int(self.db.execute(_LAST).fetchone()[0])
        except (OSError, sqlite3.Error) as error:
            raise Lost(f"T3 Code's store at {self.where} cannot be read ({error})") from None
        if last < self.sequence:
            raise Lost(f"T3 Code's store at {self.where} started its events over")
        found = []
        for sequence, thread, kind, occurred, status in rows:
            made = facet(kind, status)
            if made is not None:
                with contextlib.suppress(ValueError, TypeError):
                    found.append(Event(sequence, str(thread), made, moment(str(occurred))))
        self.moved, self.sequence = last > self.sequence, max(last, self.sequence)
        return found

    def settled(self) -> list[Event]:
        """Return the events of a write that woke the follower: read, and read again `SETTLE`
        apart until the store shows an event after the last one read, as it does once the write's
        commit is published, or the pauses run out, as for a write that commits no event."""
        found = self.read()
        for pause in SETTLE:
            if self.moved:
                break
            time.sleep(pause)
            found += self.read()
        return found

    def close(self) -> None:
        self.db.close()


def latest(events: list[Event]) -> dict[str, Event]:
    """Return the last event of each thread."""
    return {one.thread: one for one in events}


def restate(config: Config, events: list[Event]) -> list[tuple[str, str, work.Thread]]:
    """Restate each project's lines of the threads the events moved, each by its last event, and
    return the project, the key and the facet of each line changed."""
    changed = []
    for one in latest(events).values():
        for project in config.projects:
            keys = restated.followed(config.state(project), one.thread, one.facet, one.at)
            changed.extend((project.name, key, one.facet) for key in keys)
    return changed


class Waker:
    """Wakes on a write into the store's folder: inotify on Linux, a sleep of `poll` seconds
    elsewhere, and at the latest after `TICK` seconds either way."""

    IN_MODIFY, IN_CLOSE_WRITE, IN_MOVED_TO, IN_CREATE = 0x2, 0x8, 0x80, 0x100

    def __init__(self, folder: Path, poll: float = 0.25) -> None:
        self.fd, self.poll = -1, poll
        if not sys.platform.startswith("linux"):
            return
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        mask = self.IN_MODIFY | self.IN_CLOSE_WRITE | self.IN_MOVED_TO | self.IN_CREATE
        if fd >= 0 and libc.inotify_add_watch(fd, str(folder).encode(), mask) >= 0:
            self.fd = fd
        elif fd >= 0:
            os.close(fd)

    def wait(self, name: str, timeout: float = TICK) -> bool:
        """Return True once a file whose name starts with `name` was written, and False once
        `timeout` passed, or `poll` seconds where there is no inotify."""
        if self.fd < 0:
            time.sleep(min(self.poll, timeout))
            return False
        until = time.monotonic() + timeout
        while (left := until - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                return False
            if any(one.startswith(name) for one in self._names()):
                return True
        return False

    def _names(self) -> Iterator[str]:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        at = 0
        while at + 16 <= len(data):
            size = struct.unpack_from("iIII", data, at)[3]
            yield data[at + 16 : at + 16 + size].rstrip(b"\0").decode(errors="replace")
            at += 16 + size

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def _record(config: Config, since: str, lost: int, why: str) -> None:
    """Keep since when the follower follows, how often it lost its stream, and why it last did."""
    record = {"since": since, "lost": lost, **({"why": why} if why else {})}
    write_json(config.state_dir / restated.FOLLOW, record)


def follow(
    config: Config,
    say: Callable[[str], None] = print,
    stop: threading.Event | None = None,
    where: Path | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Follow T3 Code's events until `stop` is set, restating each line they move. A lost stream
    is opened again, at once and then up to `BACKOFF` seconds apart."""
    stop = stop or threading.Event()
    where = where or boxes.store()
    where.parent.mkdir(parents=True, exist_ok=True)
    waker = Waker(where.parent)
    store: Store | None = None
    since, lost, why, pause, said, woke = restated.moment(clock()), 0, "", 0.0, "", False
    try:
        while not stop.is_set():
            try:
                if store is None:
                    store = Store(where)
                    say(f"follow: T3 Code's events at {where}, from event {store.sequence}")
                    _record(config, since, lost, why)
                    pause, said = 0.0, ""
                restate(config, store.settled() if woke else store.read())
            except Lost as error:
                if store is not None:
                    store.close()
                    store, lost, why = None, lost + 1, str(error)
                    _record(config, since, lost, why)
                if str(error) != said:
                    say(f"follow: the stream is lost: {error}; opening it again")
                    said = str(error)
                stop.wait(pause)
                pause = min(BACKOFF, max(0.5, pause * 2))
                continue
            woke = waker.wait(where.name)
    finally:
        waker.close()
        if store is not None:
            store.close()
    return 0


def _follow(_: object, config: Config) -> int:
    try:
        return follow(config)
    except KeyboardInterrupt:
        return 0


VERBS = (
    verbs.Verb(
        "follow",
        "restate a thread's line of work.json as T3 Code's events say it started or ended",
        verbs.nothing,
        _follow,
    ),
)
