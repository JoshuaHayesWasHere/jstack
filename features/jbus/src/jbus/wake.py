"""jbus records what it finds as events, in a log that keeps every one, and sends no event to a
thread: a home hears jbus only from the one list of open items (`jbus.wakes`).

An event is one JSON object, `{"project", "slug", "event", "line", "text", "loud"}`. `line` is the
finding in one line, and `text` is what made it. `loud` says who should see the event, and jbus
looks `loud` up in `LOUDNESS` by the event's kind. jbus builds `LOUDNESS` at import from the
`EVENTS` that each of its modules declares at its top, so a new kind needs one line in the module
that sends it and none in this one. There are two levels. `user` is an escalation: a decision
the user has to make (`jbus.blockers`), which the one list carries to a home. `quiet` is everything
else, a fact for the record, and the digest lists the routine ones. The caller that logs an event
may give it the lower level.

`Box` keeps a project's log and the keys of everything it has logged, so jbus records a finding
only once. `Box` takes a short lock for each change, because `jbus gate` and `jbus done` add an
event while a pass runs. `notify` shows a line on the desktop, the desk, which needs no T3 Code.

Every body for the second target has a top-level `kind`: `events`, and `reminder` and `refresh`
for the timers of what blocks (`waiting.cadence`). The second target, the config's `blocking`
pair, is the one route of a box (`Box.blocking`), which jbus-relay sends on. Its outbox, in
`blocking/`, holds whole bodies, not events, and no event goes there. Each pass queues to the
second target one `events` body that lists the items that began to block in that pass, with
`items` beside `say` and `events`. The pass also queues a reminder or a refresh as each falls due.
The flush keeps the five-minute gap for the `events` body. The flush sends a reminder or a refresh
with no gap, together with every body queued before it, so the bodies go in order. A retry after
a failed POST waits on the gap, whatever the retried body holds. A refresh that waits replaces the
one before it, which is out of date.

The log is `events.jsonl`. jbus adds a line for each event when it logs the event, `{"at", "id",
"event", "slug", "loud", "line", "text"}`. A party names an event by another id, which is unique
(`entries`). The daily prune rewrites the file without its oldest lines. `Box.log` reads the
events back, and `jbus events` and the view read them from that list. `Box.record` adds a line
for what jbus keeps and never sends, such as the user's word to a home (`jbus.word`). jbus never
reads the log to decide what to send or what counts as sent. A line jbus cannot write waits in
`unlogged.json` until jbus can write its next line.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbus import LEVELS, Loud, Project, locked, read_json, refusal, sources, write_json
from jsettings import store

LOCK = "outbox.lock"
CAP = 8_000
SNAPSHOT_CAP = 32_000
GAP = 5 * 60
TIMEOUT = 8
COMMAND_TIMEOUT = 300
JMERGE_TIMEOUT = 17 * 60
SNAPSHOT_AT = (17, 15)
PRUNE_AFTER = timedelta(days=7)
LOG = "events.jsonl"
UNLOGGED = "unlogged.json"
LOG_KEEP = timedelta(days=14)
FOUND_AGAIN = ("merged", "merged-left", "retro", "stale", "gate", "condition", "settled")
BLOCKING = "blocking"
EVENTS_KIND = "events"
TIMERS = ("reminder", "refresh")
HEADER = "X-Automation-Key"
AGENT = "jbus"

EVENTS = {"heartbeat": "quiet", "snapshot": "quiet"}


def _events(name: str, source: str) -> dict[str, Loud]:
    """Return what a module's source declares: its `EVENTS`, as `jbus.sources.statement` finds
    it, `EVENTS = {...}` or `EVENTS: <type> = {...}`. A value there that is not such a dict
    raises a `ValueError` that names the module."""
    try:
        node = sources.statement(source, "EVENTS")
        if node is None:
            return {}
        found = ast.literal_eval(node.value)
    except (ValueError, TypeError, SyntaxError):
        found = None
    if not isinstance(found, dict) or not all(
        isinstance(kind, str) and level in LEVELS for kind, level in found.items()
    ):
        raise ValueError(
            f"{name}: EVENTS is not a dict written out, of kinds each at one of {LEVELS}"
        )
    return found


def declared(paths: Iterable[str]) -> dict[str, Loud]:
    """Return every kind that the modules under `paths` declare, each at its level. A module
    declares what it sends at its top, written out as `EVENTS = {"<kind>": "<level>"}`.
    `declared` reads that off the module's source and imports nothing, so it can read a
    module that imports this one. If two modules declare the same kind, it raises a
    `ValueError` that names both."""
    table: dict[str, Loud] = {}
    by: dict[str, str] = {}
    for name, source in sources.modules(paths, f"{jbus.__name__}.", deep=True):
        for kind, level in _events(name, source).items():
            if kind in by:
                raise ValueError(f"{kind} is declared in {by[kind]} and in {name}")
            table[kind], by[kind] = level, name
    return table


LOUDNESS = declared(jbus.__path__)


def cut(text: str, cap: int = CAP) -> str:
    return text if len(text) <= cap else text[: cap - len("[cut]")] + "[cut]"


def event(
    project: str,
    slug: str,
    kind: str,
    line: str,
    text: str = "",
    cap: int = CAP,
    loud: Loud | None = None,
) -> dict:
    """Return one event, at its kind's level or at `loud`, a lower one. A kind that `LOUDNESS` does
    not name raises a `KeyError`, and a level above the kind's raises a `ValueError`."""
    level = LOUDNESS[kind]
    if loud is not None and LEVELS.index(loud) < LEVELS.index(level):
        raise ValueError(f"{kind} is {level}: it cannot be sent as {loud}")
    made = {"project": project, "slug": slug, "event": kind, "line": line, "text": cut(text, cap)}
    return {**made, "loud": loud or level}


def _at(now: datetime) -> str:
    return jsettings.stamp(now)


def _id(one: dict[str, Any]) -> str:
    """Return the id of an event in the log. Two equal events get the same id."""
    return hashlib.sha256(json.dumps(one, sort_keys=True).encode()).hexdigest()[:16]


def notify(line: str) -> None:
    """Raise a desktop notification on this machine, which needs no T3 Code.

    It does nothing without `notify-send`, and one that fails does not fail the pass.
    """
    command = shutil.which("notify-send")
    if command:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run([command, "jbus", line], capture_output=True, timeout=5)


@dataclass(frozen=True)
class Route:
    """A `Route` is the second target, the place that gets a project's bodies, with the folder that
    holds its `outbox.json` and its `wake.json`, its URL and its key."""

    folder: Path
    url: str = ""
    key: str = ""
    blocking: bool = False


class Box:
    """A `Box` holds a project's log, the keys of what it has logged, and its second target's
    outbox.

    The project's `wake.json` holds the marks: `began`, the day of the last `snapshot`, the
    day whose sweep has not run yet (`sweep_owed`), and the last `sweep`. A route's `wake.json`
    holds its own `posted` and why its last send failed (`last_error`), which is empty once a send
    goes through. `wake.json` does not count how many sends failed in a row: that is a streak, and
    `jbus.alert` keeps streaks.
    """

    def __init__(self, state: Path, project: Project, second: jbus.Hook = ("", "")) -> None:
        self.state = state
        self.project = project
        self.second = second

    @property
    def blocking(self) -> Route | None:
        """Return the second target, where the config sets it: a route that gets no event."""
        if not self.second[0]:
            return None
        return Route(self.state / BLOCKING, *self.second, blocking=True)

    @staticmethod
    def clock() -> datetime:
        """Return the time that jbus stamps on a line of the log."""
        return datetime.now(UTC)

    def sent(self) -> list[str]:
        """Return the keys of everything ever sent."""
        return read_json(self.state / "sent.json", [])

    def send(
        self,
        slug: str,
        kind: str,
        line: str,
        text: str = "",
        *,
        key: str | None = None,
        cap: int = CAP,
        loud: Loud | None = None,
    ) -> bool:
        """Log one event. With a key, `send` only ever logs the first event of that key, and
        returns False for a key that was logged before. If jbus cannot write the event's line,
        the line is owed: jbus writes it into the log before any later line, as soon as it can
        write again."""
        made = event(self.project.name, slug, kind, line, text, cap, loud)
        with locked(self.state, LOCK):
            if key is not None:
                sent = self.sent()
                if key in sent:
                    return False
                write_json(self.state / "sent.json", [*sent, key])
            took = {"event": kind, "slug": slug, "loud": made["loud"], "line": line}
            self._log(id=_id(made), **took, text=made["text"], owed=True)
        return True

    def record(self, kind: str, line: str, text: str = "", **more: Any) -> None:
        """Add a line to the log for what jbus keeps and never sends, such as the user's word."""
        with locked(self.state, LOCK):
            record = {"event": kind, "slug": "", "loud": "quiet", "line": line}
            self._log(owed=True, **record, text=cut(text), **more)

    def _log(self, owed: bool = False, **record: Any) -> None:
        """Add one line to the log, which only the log's owner reads. The caller holds the lock.

        jbus leaves out a line that it cannot write, and the pass goes on without it. A line that
        is `owed` waits in `unlogged.json`, and jbus writes it before the next line that it can
        write.
        """
        record = {"at": _at(self.clock()), **record}
        waiting = read_json(self.state / UNLOGGED, [])
        try:
            store.append_jsonl(self.state / LOG, [*waiting, record], mode=0o600, sort_keys=True)
        except OSError:
            if owed:
                write_json(self.state / UNLOGGED, [*waiting, record], mode=0o600)
            return
        if waiting:
            (self.state / UNLOGGED).unlink(missing_ok=True)

    def log(self) -> list[dict[str, Any]]:
        """Return every event the log holds, oldest first, each with the `id` a party names it
        by (`entries`). `log` takes no lock and writes nothing."""
        return entries(self.state)

    def forget(self, before: datetime) -> None:
        """Drop the log's lines from before this moment."""
        with locked(self.state, LOCK):
            path = self.state / LOG
            records = _records(path)
            kept = [one for one in records if datetime.fromisoformat(one["at"]) >= before]
            if len(kept) < len(records):
                temporary = path.with_name(path.name + ".tmp")
                handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    for one in kept:
                        os.write(handle, (json.dumps(one, sort_keys=True) + "\n").encode())
                    os.fsync(handle)
                finally:
                    os.close(handle)
                os.replace(temporary, path)

    def mark(self, key: str) -> None:
        """Record a key as sent, sending nothing, for what was already so on the first pass."""
        with locked(self.state, LOCK):
            sent = self.sent()
            if key not in sent:
                write_json(self.state / "sent.json", [*sent, key])

    def began(self) -> None:
        """Record that a whole pass has run for this project: from now on jbus sends what is new.
        `began` removes the marks of the old webhook, `posted` and `last_error`, which an earlier
        pass left there."""
        with locked(self.state, LOCK):
            marks = read_json(self.state / "wake.json", {})
            kept = {**marks, "began": True}
            for old in ("posted", "last_error", "failed", "alerted"):
                kept.pop(old, None)
            if kept != marks:
                write_json(self.state / "wake.json", kept)

    def snapshot_due(self, local: datetime) -> str | None:
        """Return the day whose snapshot has not gone yet, at or after 5:15 PM. `local` is
        now, in the user's zone."""
        day = local.date().isoformat()
        if (local.hour, local.minute) < SNAPSHOT_AT:
            return None
        return None if read_json(self.state / "wake.json", {}).get("snapshot") == day else day

    def snapshot_sent(self, day: str) -> None:
        """Record that the day's snapshot went out, and that the day's sweep is now owed."""
        with locked(self.state, LOCK):
            marks = read_json(self.state / "wake.json", {})
            write_json(self.state / "wake.json", {**marks, "snapshot": day, "sweep_owed": day})

    def sweep_owed(self) -> str | None:
        """Return the day whose sweep has not run yet. jbus keeps that day until a sweep runs."""
        return read_json(self.state / "wake.json", {}).get("sweep_owed")

    def swept(self, sweep: str, ran: bool) -> None:
        """Record how the owed sweep went. A sweep that ran is owed no more."""
        with locked(self.state, LOCK):
            marks = {**read_json(self.state / "wake.json", {}), "sweep": sweep}
            if ran:
                marks.pop("sweep_owed", None)
            write_json(self.state / "wake.json", marks)

    def prune(self, slugs: set[str]) -> None:
        """Forget the keys that name one of these slugs, except those of a kind in `FOUND_AGAIN`."""
        with locked(self.state, LOCK):
            sent = self.sent()
            kept = [key for key in sent if not _prunable(key, slugs)]
            if len(kept) < len(sent):
                write_json(self.state / "sent.json", kept)

    def marks(self, route: Route | None = None) -> dict[str, Any]:
        """Return the marks of the second target's route, or by default the project's, which sit
        in the project's state folder."""
        return read_json((route.folder if route else self.state) / "wake.json", {})

    def drop(self, folder: str) -> None:
        """Remove a route's outbox and marks, `BLOCKING`'s, once the config has no second target."""
        with locked(self.state, LOCK):
            shutil.rmtree(self.state / folder, ignore_errors=True)

    def post(self, made: dict[str, Any]) -> None:
        """Queue one whole body for the second target. A refresh replaces a refresh that
        still waits. With no second target, `post` queues nothing."""
        route = self.blocking
        if route is None:
            return
        with locked(self.state, LOCK):
            waiting = read_json(route.folder / "outbox.json", [])
            if made["kind"] == "refresh":
                waiting = [one for one in waiting if one.get("kind") != "refresh"]
            write_json(route.folder / "outbox.json", [*waiting, made], mode=0o600)

    def waiting(self, route: Route) -> int:
        return len(read_json(route.folder / "outbox.json", []))

    def flush_blocking(
        self, now: datetime, say=print, *, went: Callable[[str], None] = lambda _: None
    ) -> int:
        """Post the bodies that wait for the second target, in order. They go once the gap has
        passed since the target's last POST, or at once when a reminder or a refresh waits and
        the last POST did not fail. A retry waits on the gap, as on every route. Each body
        gets one try, and the first that fails ends the flush. Return how many went. It calls
        `went` with how the flush ended: nothing for the bodies that went, and the reason for
        the one that failed."""
        route = self.blocking
        if route is None:
            return 0
        outbox, wakes = route.folder / "outbox.json", route.folder / "wake.json"
        with locked(self.state, LOCK):
            waiting = read_json(outbox, [])
            marks = read_json(wakes, {})
            if not waiting:
                return 0
            fresh = not marks.get("last_error")
            timed = fresh and any(one.get("kind") in TIMERS for one in waiting)
            if not timed and now.timestamp() - marks.get("posted", 0) < GAP:
                return 0
            marks = {**marks, "posted": now.timestamp()}
            write_json(wakes, marks)
            sent, why = 0, ""
            for one in waiting:
                why = _post_blocking(route, one)
                if why:
                    break
                sent += 1
                self._log(posted_blocking=one["kind"], items=len(one.get("items", [])))
                write_json(outbox, waiting[sent:], mode=0o600)
            write_json(wakes, {**marks, "last_error": why})
            if why:
                say(f"wake failed {self.project.name} {BLOCKING}: {why}")
        if sent:
            went("")
        if why:
            went(why)
        return sent


def _records(path: Path) -> list[dict[str, Any]]:
    """Return the log's lines that are a record with a time, and leave out any other line."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
            datetime.fromisoformat(record["at"])
        except (ValueError, KeyError, TypeError):
            continue
        records.append(record)
    return records


def entries(state: Path) -> list[dict[str, Any]]:
    """Every event of the project's log in the order of the file, each with its `id`: the one id
    a party names an event by, as the event it last saw (a go's `seen`) or as the feed's cursor
    (`jbus.cursor`).

    The id is a hash of the line as the file holds it and of how many equal lines come before
    it, so two equal events have two ids. The file only grows, apart from the daily prune
    (`Box.forget`), which writes each line it keeps as it was and drops equal lines together,
    since they have one time: an id names the same line across restarts and prunes. A line
    jbus owed (`UNLOGGED`) is written late with its first time, so the prune can drop it before
    a party that read past it reads it."""
    before: dict[str, int] = {}
    return [
        record | {"id": _entry(record, before)}
        for record in _records(state / LOG)
        if "event" in record
    ]


def _entry(record: dict[str, Any], before: dict[str, int]) -> str:
    """The id of an event line (`entries`), counting it in `before`, the equal lines read so
    far."""
    line = json.dumps(record, sort_keys=True)
    before[line] = before.get(line, 0) + 1
    return hashlib.sha256(f"{line}#{before[line]}".encode()).hexdigest()[:16]


def _prunable(key: str, slugs: set[str]) -> bool:
    kind, _, rest = key.partition("|")
    return kind not in FOUND_AGAIN and rest.partition("|")[0] in slugs


def _post_blocking(route: Route, made: dict[str, Any]) -> str:
    """POST one body to the second target. Return why it failed, with no URL and no key in it,
    or nothing."""
    url, key = route.url, route.key
    request = urllib.request.Request(
        url,
        data=json.dumps(made).encode(),
        headers={
            "content-type": "application/json",
            "Authorization": f"Bearer {key}",
            HEADER: key,
            "User-Agent": AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            reply.read()
    except urllib.error.HTTPError as error:
        return f"the second target answered {error.code}{refusal.said(error, url, key)}"
    except TimeoutError:
        return f"no answer in {TIMEOUT} s"
    except urllib.error.URLError as error:
        timed = isinstance(error.reason, TimeoutError)
        return f"no answer in {TIMEOUT} s" if timed else "the second target could not be reached"
    except (OSError, ValueError):
        return "the second target could not be reached"
    return ""
