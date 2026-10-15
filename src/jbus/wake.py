"""Telling the user: events, the log every one is written to, and the POSTs for the few that
ask something of them.

An event is one JSON object, `{"project", "slug", "event", "line", "text", "loud"}`. `line`
is the one line a finding is, and `text` is what made it. `loud` is whom the event is for,
read off `LOUDNESS` by its kind. `LOUDNESS` is built at import from the `EVENTS` each module
of jbus declares at its top, so a new kind is a line in its own module and none here. There
are two levels. `user` is an escalation: a new
question, a hold or an approval that is theirs, an alert, a stall. Such an event waits in
the outbox for the next POST, and also has `say`, the line to post in the chat as it is,
which begins with the project whose home the user acts in. `quiet` is everything else, a
fact for the record: it is written to the log and never posted. The one who queues an event
may give it the lower level: a `waiting` event that asks nothing new of the user is `quiet`.

`Box` keeps a project's outbox and the keys of what was ever sent, so a finding goes once,
and holds a short lock for each change: `jbus gate` and `jbus done` add an event while a
pass runs. `notify` tells the desk what the webhook could not be told.

An event for the user goes to each of the project's `routes`: its own webhook, and the
top-level one, the monitor of every project, when that is set and is not the same pair. Each
route has its own outbox, five-minute gap and `last_error`, in its own folder: the project's
state for its own webhook, `top-level/` in it for the other. So one webhook that is down
neither holds nor repeats what the other is posted.

The log is `events.jsonl`. A line is added for an event as it was queued, `{"at", "id",
"event", "slug", "loud", "line", "text"}`, and for a POST that was taken, `{"at", "posted":
[ids]}`, and the daily prune rewrites the file without its oldest lines. Both times are the
clock's, so a POST is never before what it carries. A POST to the top-level webhook is
`{"at", "posted_top_level": [ids]}`, so `posted` stays what the project's own webhook took.
The id is a hash of the event as the outbox holds it, so the outbox and the POST carry
nothing for the log. `Box.log` reads the two kinds of line back as one list: `jbus events`
and the view read a quiet event from there. `Box.record` adds a line for what is kept and
never posted, as the user's word to a home is (`jbus.word`): it is in the log and in no
outbox. The log never decides what is sent or what counts as sent: a line that cannot be
written is left out, but for one that is in no outbox, which waits in `unlogged.json` for
the next line that can be written.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import fcntl
import hashlib
import json
import os
import pkgutil
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jbus
from jbus import LEVELS, Config, Loud, Project, queue, read_json, verbs, write_json

CAP = 8_000
WAKE_CAP = 100_000
SNAPSHOT_CAP = 32_000
GAP = 5 * 60
TIMEOUT = 8
SNAPSHOT_AT = (17, 15)
PRUNE_AFTER = timedelta(days=7)
LOG = "events.jsonl"
UNLOGGED = "unlogged.json"
LOG_KEEP = timedelta(days=14)
FOUND_AGAIN = ("merged", "merged-left", "retro", "stale", "gate", "condition", "settled")
TOP_LEVEL = "top-level"
HEADER = "X-Automation-Key"
AGENT = "jbus"
CONDITION = "condition"

EVENTS = {"condition": "quiet", "heartbeat": "quiet", "snapshot": "quiet"}


def _sources(paths: Iterable[str], prefix: str) -> Iterator[tuple[str, str]]:
    """Every module under `paths`, those in its folders too, as its name and its source."""
    for module in pkgutil.iter_modules(paths, prefix):
        spec = module.module_finder.find_spec(module.name)
        yield module.name, spec.loader.get_source(module.name)
        if module.ispkg:
            yield from _sources(spec.submodule_search_locations, f"{module.name}.")


def _events(name: str, source: str) -> dict[str, Loud]:
    """What a module's source declares. One form is read: the first statement at the top of
    the module that sets the name `EVENTS` alone, `EVENTS = {...}` or `EVENTS: <type> = {...}`.
    A value there that is not such a dict is a `ValueError` that names the module. No other
    statement is a declaration, and none is read: `EVENTS` among the names of a tuple, set
    under an `if` or a `try`, added to with `|=`, or set a second time lower down."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if "EVENTS" not in map(ast.unparse, targets):
            continue
        try:
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
    return {}


def declared(paths: Iterable[str]) -> dict[str, Loud]:
    """Every kind the modules under `paths` declare, each at its level. A module declares
    what it sends at its top, as `EVENTS = {"<kind>": "<level>"}` written out. It is read
    off the module's source and nothing is imported, so a module that imports this one is
    read all the same. A kind two modules declare is a `ValueError` that names both."""
    table: dict[str, Loud] = {}
    by: dict[str, str] = {}
    for name, source in _sources(paths, f"{jbus.__name__}."):
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
    """One event, at its kind's level or at `loud`, a lower one. A kind `LOUDNESS` does not
    name is a `KeyError`, and a level above the kind's is a `ValueError`. What it says in
    the chat names the project: one webhook is posted every project's. A line that begins
    `<kind> <project>:` names it already, and is said as it is."""
    level = LOUDNESS[kind]
    if loud is not None and LEVELS.index(loud) < LEVELS.index(level):
        raise ValueError(f"{kind} is {level}: it cannot be sent as {loud}")
    loud = loud or level
    made = {"project": project, "slug": slug, "event": kind, "line": line, "text": cut(text, cap)}
    named = line.startswith(f"{kind} {project}:")
    say = line if named else f"{project}: {line}"
    return {**made, "loud": loud} | ({"say": say} if loud == "user" else {})


def renamed(line: str, names: dict[str, str]) -> str:
    """A line begins with the kind of its event: one that begins with an old kind has the new.
    `names` is `jbus.old_names`."""
    kind, space, rest = line.partition(" ")
    now = jbus.current_kind(kind, names)
    return (now if now in LOUDNESS else kind) + space + rest


def current(one: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """An event read from disk, with its kind, its level and its lines by the names of now.
    `names` is `jbus.old_names`."""
    read = {"event": jbus.current_kind, "loud": jbus.current_level}
    now = {key: by(one[key], names) for key, by in read.items() if isinstance(one.get(key), str)}
    lines = {
        key: renamed(one[key], names) for key in ("line", "say") if isinstance(one.get(key), str)
    }
    return {**one, **now, **lines}


def _key(key: str, names: dict[str, str]) -> str:
    """A key of what was sent, with the kind it starts with by the name it has now."""
    kind, bar, rest = key.partition("|")
    return jbus.current_kind(kind, names) + bar + rest


def _loud(one: dict[str, Any]) -> Loud:
    """Whom an event is for. One queued before events said so is of its kind's level."""
    return one.get("loud") or LOUDNESS.get(one.get("event", ""), "quiet")


def _at(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="seconds")


def _id(one: dict[str, Any]) -> str:
    """What names an event in the log: two that are the same in the outbox share it."""
    return hashlib.sha256(json.dumps(one, sort_keys=True).encode()).hexdigest()[:16]


def notify(line: str) -> None:
    """Raise a desktop notification on this machine, which needs no webhook.

    Skipped where there is no `notify-send`, and one that fails does not fail the pass.
    """
    command = shutil.which("notify-send")
    if command:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run([command, "jbus", line], capture_output=True, timeout=5)


@dataclass(frozen=True)
class Route:
    """One webhook a project's events for the user are posted to, and the folder that holds
    its `outbox.json` and its `wake.json`. `top` is the top-level webhook, posted beside the
    project's own."""

    url: str
    key: str
    folder: Path
    top: bool = False


class Box:
    """A project's outboxes, the keys of what it has sent, and when it last posted.

    `wake.json` holds the marks: `began`, `posted`, the day of the last `snapshot`, the
    day whose sweep has not run yet (`sweep_owed`), the last `sweep`, and why the last POST
    failed (`last_error`), which is nothing once one is sent. How many failed in a row is
    not kept here: that is a streak, and `jbus.alert` keeps those. The top-level route's
    `wake.json` holds only its own `posted` and `last_error`.

    `top` is the config's top-level pair. It is a route of its own when it is set and is not
    the project's pair: a project with none of its own was given it already, and is posted it
    once.
    """

    def __init__(self, state: Path, project: Project, top: jbus.Hook = ("", "")) -> None:
        self.state = state
        self.project = project
        self.top = top

    @property
    def routes(self) -> list[Route]:
        """The project's own webhook, then the top-level one where it is a route of its own."""
        own = Route(self.project.webhook_url, self.project.webhook_key, self.state)
        other = Route(*self.top, self.state / TOP_LEVEL, top=True)
        mine = (own.url, own.key)
        return [own, *([other] if self.top[0] and tuple(self.top) != mine else [])]

    @staticmethod
    def clock() -> datetime:
        """The time a line of the log is written with."""
        return datetime.now(UTC)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.state.mkdir(parents=True, exist_ok=True)
        with open(self.state / "outbox.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _outbox(self, route: Route | None = None) -> list[dict[str, Any]]:
        folder = (route or self.routes[0]).folder
        names = jbus.old_names()
        return [current(one, names) for one in read_json(folder / "outbox.json", [])]

    def sent(self) -> list[str]:
        """The keys of what was ever sent."""
        names = jbus.old_names()
        return [_key(key, names) for key in read_json(self.state / "sent.json", [])]

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
        """Queue one event. With a key, only the first event of that key is ever queued.

        One for the user waits in the outbox of each route for a POST. A quiet one is only
        logged, so the log is its one record: where its line cannot be written it is owed,
        and goes into the log, before any later line, as soon as one can be written. The
        answer is False only for a key that was sent before.
        """
        made = event(self.project.name, slug, kind, line, text, cap, loud)
        with self._locked():
            if key is not None:
                sent = self.sent()
                if key in sent:
                    return False
                write_json(self.state / "sent.json", [*sent, key])
            if made["loud"] == "user":
                for route in self.routes:
                    route.folder.mkdir(parents=True, exist_ok=True)
                    waiting = [*self._outbox(route), made]
                    write_json(route.folder / "outbox.json", waiting, mode=0o600)
            took = {"event": kind, "slug": slug, "loud": made["loud"], "line": line}
            self._log(id=_id(made), **took, text=made["text"], owed=made["loud"] != "user")
        return True

    def record(self, kind: str, line: str, text: str = "", **more: Any) -> None:
        """Add a line to the log for what is never posted: it goes into no outbox."""
        with self._locked():
            record = {"event": kind, "slug": "", "loud": "quiet", "line": line}
            self._log(owed=True, **record, text=cut(text), **more)

    def _log(self, owed: bool = False, **record: Any) -> None:
        """Add one line to the log, which only its owner reads. The caller holds the lock.

        A line that cannot be written is left out: the outbox and the POST go on without
        it. One that is `owed`, which is in no outbox, waits in `unlogged.json` and is
        written before the next line that can be.
        """
        record = {"at": _at(self.clock()), **record}
        waiting = read_json(self.state / UNLOGGED, [])
        lines = [json.dumps(one, sort_keys=True) + "\n" for one in [*waiting, record]]
        try:
            handle = os.open(self.state / LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(handle, "".join(lines).encode())
            finally:
                os.close(handle)
        except OSError:
            if owed:
                write_json(self.state / UNLOGGED, [*waiting, record], mode=0o600)
            return
        if waiting:
            (self.state / UNLOGGED).unlink(missing_ok=True)

    def log(self) -> list[dict[str, Any]]:
        """Every event the log holds, oldest first, each with `posted`: when, or None.

        A POST names its events by id, and the outbox goes in order, so it is the oldest
        event of that id not yet posted that went. It takes no lock and writes nothing.
        """
        events: list[dict[str, Any]] = []
        waiting: dict[str, list[dict[str, Any]]] = {}
        names = jbus.old_names()
        for record in _records(self.state / LOG):
            if "posted" in record:
                for name in record["posted"]:
                    if waiting.get(name):
                        waiting[name].pop(0)["posted"] = record["at"]
            elif "event" in record:
                one = {**current(record, names), "posted": None}
                events.append(one)
                waiting.setdefault(one.pop("id", ""), []).append(one)
        return events

    def forget(self, before: datetime) -> None:
        """Drop the log's lines from before this moment."""
        with self._locked():
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
        """Record a key as sent with nothing sent: what was already so on the first pass."""
        with self._locked():
            sent = self.sent()
            if key not in sent:
                write_json(self.state / "sent.json", [*sent, key])

    def began(self) -> None:
        """A whole pass has run for this project: from now on what is new is sent."""
        with self._locked():
            marks = read_json(self.state / "wake.json", {})
            if not marks.get("began"):
                write_json(self.state / "wake.json", {**marks, "began": True})

    def snapshot_due(self, local: datetime) -> str | None:
        """The day whose snapshot has not gone yet, at or after 5:15 PM. `local` is now, in
        the user's zone."""
        day = local.date().isoformat()
        if (local.hour, local.minute) < SNAPSHOT_AT:
            return None
        return None if read_json(self.state / "wake.json", {}).get("snapshot") == day else day

    def snapshot_sent(self, day: str) -> None:
        """The day's snapshot has gone, and the day's look at what a sweep removes is owed."""
        with self._locked():
            marks = read_json(self.state / "wake.json", {})
            write_json(self.state / "wake.json", {**marks, "snapshot": day, "sweep_owed": day})

    def sweep_owed(self) -> str | None:
        """The day whose sweep has not run yet: it keeps that day until one runs."""
        return read_json(self.state / "wake.json", {}).get("sweep_owed")

    def swept(self, sweep: str, ran: bool) -> None:
        """How the owed sweep went. One that ran is owed no more."""
        with self._locked():
            marks = {**read_json(self.state / "wake.json", {}), "sweep": sweep}
            if ran:
                marks.pop("sweep_owed", None)
            write_json(self.state / "wake.json", marks)

    def prune(self, slugs: set[str]) -> None:
        """Forget the keys that name one of these slugs, but for what is found again."""
        with self._locked():
            sent = self.sent()
            kept = [key for key in sent if not _prunable(key, slugs)]
            if len(kept) < len(sent):
                write_json(self.state / "sent.json", kept)

    def marks(self, route: Route | None = None) -> dict[str, Any]:
        """The marks of a route, the project's own by default, and `failed`: 1 while its last
        POST failed, for what asks only that."""
        marks = read_json((route or self.routes[0]).folder / "wake.json", {})
        return {**marks, "failed": int(bool(marks.get("last_error")))}

    def drop_top_level(self) -> None:
        """Remove the top-level route's outbox and marks, once the project has no such route."""
        with self._locked():
            shutil.rmtree(self.state / TOP_LEVEL, ignore_errors=True)

    def waiting(self, route: Route | None = None) -> int:
        return len(self._outbox(route))

    def flush(
        self,
        now: datetime,
        say=print,
        *,
        route: Route | None = None,
        went: Callable[[str], None] = lambda _: None,
    ) -> int:
        """Post what waits for one route, the project's own by default, in order, at most once
        in five minutes. The answer is how many went.

        Only an event for the user waits there. One of another level, which an outbox from
        before quiet events were only logged may hold, leaves it here and is not posted.

        What waits goes in lists of at most `WAKE_CAP` bytes of JSON, one after another, and
        each list that is sent leaves the outbox at once. The first that fails ends the flush:
        it and what follows it wait for the next one. One try for each list.

        `went` hears how a flush that posted ended, after the outbox is unlocked: nothing for
        lists that were sent, and why for the one that failed. It hears both when both happened.
        """
        route = route or self.routes[0]
        outbox, wakes = route.folder / "outbox.json", route.folder / "wake.json"
        with self._locked():
            waiting = self._outbox(route)
            marks = read_json(wakes, {})
            taken = [one for one in waiting if _loud(one) == "user"]
            if len(taken) < len(waiting):
                waiting = taken
                write_json(outbox, waiting, mode=0o600)
            if not waiting:
                return 0
            if now.timestamp() - marks.get("posted", 0) < GAP:
                return 0
            marks.pop("failed", None)
            marks.pop("alerted", None)
            marks = {**marks, "posted": now.timestamp()}
            write_json(wakes, marks)
            sent, why = 0, ""
            logged = "posted_top_level" if route.top else "posted"
            for some in _lists(waiting):
                why = _post(route, some)
                if why:
                    break
                sent += len(some)
                self._log(**{logged: [_id(one) for one in some]})
                write_json(outbox, waiting[sent:], mode=0o600)
            write_json(wakes, {**marks, "last_error": why})
            if why:
                which = f" {TOP_LEVEL} webhook" if route.top else ""
                say(f"wake failed {self.project.name}{which}: {why}")
        if sent:
            went("")
        if why:
            went(why)
        return sent


def _records(path: Path) -> list[dict[str, Any]]:
    """The log's lines that are a record with a time. A line that is not is left out."""
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


def _prunable(key: str, slugs: set[str]) -> bool:
    kind, _, rest = key.partition("|")
    return kind not in FOUND_AGAIN and rest.partition("|")[0] in slugs


def body(events: list[dict[str, Any]]) -> dict[str, Any]:
    """What one POST carries: the lines for the chat, as they are to be posted, and the events.

    An event that was queued before events had `say` is said by its line.
    """
    say = [one.get("say") or one["line"] for one in events]
    return {"say": say, "events": events}


def _lists(events: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """The events in order, in lists whose POST is at most `WAKE_CAP` bytes. One larger is alone."""
    some: list[dict[str, Any]] = []
    for one in events:
        if some and len(json.dumps(body([*some, one])).encode()) > WAKE_CAP:
            yield some
            some = []
        some.append(one)
    if some:
        yield some


def _post(route: Route, events: list[dict[str, Any]]) -> str:
    """Send the list to the route's webhook. The answer is why it failed, with no URL and
    no key in it, or nothing."""
    url, key = route.url, route.key
    if not url:
        return "the config has no webhook_url"
    request = urllib.request.Request(
        url,
        data=json.dumps(body(events)).encode(),
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
        return f"the webhook answered {error.code}"
    except TimeoutError:
        return f"no answer in {TIMEOUT} s"
    except urllib.error.URLError as error:
        timed = isinstance(error.reason, TimeoutError)
        return f"no answer in {TIMEOUT} s" if timed else "the webhook could not be reached"
    except (OSError, ValueError):
        return "the webhook could not be reached"
    return ""


@dataclass(frozen=True)
class Changed:
    """A brief that changed after its approval: the first 12 of the sha it has now."""

    sha: str


@dataclass(frozen=True)
class Depends:
    """A row that waits for slugs that are not merged."""

    slugs: tuple[str, ...]


@dataclass(frozen=True)
class Slot:
    """A row that only a slot or room on the machine stops."""


Reason = Changed | Depends | Slot


@dataclass
class Pass:
    """One pass over one project: what every step of it shares.

    A finding is sent with `find`, once per key. What no rule covers is a `condition`, a
    quiet event that asks the user nothing. `gate` records one for a slug and leaves the
    slug alone for the rest of the pass: it is in `gated`, its row is at `gate`, and `asked`
    keeps what the condition is. `held` is the rows whose gate a full pass held back.
    `reasons` is why an approved row was not launched, which `dispatch` records once it has
    judged the row.

    A slug that `jbus queue remove` took out is gone for good: `removed` reads the names
    from `removed.json` each time it is asked, and `find` sends nothing for one of them.
    Its pull request, if one is opened later, is still a pull request to every step.

    `told` is the slugs whose thread this pass told to carry on: they wait on it, not on the
    user.
    """

    config: Config
    project: Project
    now: datetime
    say: Callable[[str], None] = print
    gated: set[str] = field(default_factory=set)
    reasons: dict[str, Reason] = field(default_factory=dict)
    asked: dict[str, str] = field(default_factory=dict)
    held: set[str] = field(default_factory=set)
    told: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.state = self.config.state(self.project)
        self.home = self.config.home(self.project)
        self.box = Box(self.state, self.project, self.config.webhook)
        self.first = not read_json(self.state / "wake.json", {}).get("began")
        self.user = self.config.user
        self.day = self.user.day(self.now)

    def run(self, *command: str) -> subprocess.CompletedProcess[str]:
        """Run a command in the project's main checkout. One that is missing fails like any."""
        try:
            return subprocess.run(
                command, cwd=self.project.checkout, capture_output=True, text=True, timeout=300
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return subprocess.CompletedProcess(command, 127, "", str(error))

    @property
    def removed(self) -> frozenset[str]:
        return queue.removed_slugs(self.state)

    def find(
        self, slug: str, kind: str, line: str, text: str = "", *, key: str = "", past: bool = False
    ) -> bool:
        """Send a finding once. One about the past is only recorded on a project's first pass,
        and one about a removed slug is only recorded, never sent."""
        key = f"{kind}|{slug}|{key or line}"
        if slug in self.removed:
            self.box.mark(key)
            return False
        if past and self.first:
            self.box.mark(key)
            return False
        return self.box.send(slug, kind, line, text, key=key)

    def condition(self, slug: str, what: str, text: str = "", *, key: str = "") -> bool:
        """Record what jbus found that no rule covers, once. It is true when it was new."""
        return self.find(slug, CONDITION, f"{CONDITION} {slug}: {what}", text, key=key)

    def gate(self, slug: str, what: str, text: str = "", *, key: str = "") -> None:
        self.gated.add(slug)
        self.asked[slug] = what
        self.condition(slug, what, text, key=key)


def _done(args: argparse.Namespace, config: Config) -> int:
    """`jbus done`: a thread with no home says its result here, and it goes at once."""
    project = verbs.here(config, args.project)
    run = Pass(config, project, datetime.now(UTC))
    text = sys.stdin.read().strip()
    if not text:
        raise jbus.Refused("refused: no lines on stdin")
    line = f"result {args.slug}: {text.splitlines()[0]}"
    new = run.find(args.slug, "result", line, text, key=f"piped {queue.sha(text)[:16]}")
    print("queued" if new else "already sent")
    return 0


def _slug(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")


VERBS = (verbs.Verb("done", "send a result now, its lines on stdin", _slug, _done),)
