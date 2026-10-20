"""`jbus relay`: take what jbus posts on 127.0.0.1 and send it on to Sous Chef, never dropping
a body without a line in the journal.

The relay listens on `RELAY_PORT` (4390) of 127.0.0.1, or on a free port it picks for 0, and
names the port it bound in the line `relay: listening on 127.0.0.1:<port>`. It takes a POST
whose `X-Automation-Key` is `RELAY_INBOUND_KEY` and whose body is one JSON object. Each body it
takes has an id: the body's own `id` when that is a short name, else a hash of the body, so a
body posted twice has one id. Each route of `ROUTES` picks what it sends of the body, and the
picked body, with `relay: {"id", "route"}` beside its keys, is written to the route's spool
before the relay answers 202. A route's sender thread posts its spool in order, off the
request path and with a timeout, so a webhook that is slow or down never holds back the next
body. A body it posted is put in the route's `sent` file, with the time, and taken out of the
spool; one that failed stays, the journal gets `relay: POST to <target> (<route>) failed for
event <id>: <why>`, and it goes again after `RELAY_RETRY_SECONDS` or when the next body comes.
A 4xx would never go, so the body moves to `dead/<route>/`, with a line, and the bodies behind
it go on; but for `AGAIN`, a key or an address the target refuses (401, 403, 404, 407), which
is its setting, and 408 and 429, which pass: those stay to go again. An own id a route sent is
never spooled again. A hashed id is not spooled again while the route holds it or sent it in
the last `RELAY_DEDUP_SECONDS` (900): that is jbus posting again a body whose answer it lost.
jbus's bodies carry no time, so a hashed id says only what the body says, and the same alert
said again later is a new event: the window is what lets it go. A POST taken and
not yet in `sent` when the relay stops goes once more after its start: the relay sends at
least once.

Both routes go to the one target, Sous Chef (`GROK_WEBHOOK_URL`, `GROK_WEBHOOK_KEY`):
`everything`, every body as it came, and `blocking`, what blocks (`blocking`). A target whose
URL or key is missing, empty or REPLACE_ME, or a missing inbound key, is refused at start: the
relay names each such key in the journal, never its value, and exits 2, which
`jbus-relay.service` does not restart. State is in `RELAY_STATE`, ~/.local/state/jbus-relay:
`spool/<route>/`, `sent/<route>`, `dead/<route>/`, `watch.json` and `heartbeat.json`.

The heartbeat is `heartbeat.json`, written each `BEAT_SECONDS`, on each body taken, and when a
route begins or ends to fail: `beat`, when it was written; `started`, when this relay started;
`heard`, when the relay last took a body, kept across a restart; `silent_minutes`,
`RELAY_SILENT_MINUTES` (90), how long with no body is silence; `failing`, each route whose
last POST failed and was not followed by one that went, with when it began to fail, why, and
how many bodies wait, kept across a restart while the route still holds a body, and ended by
a body refused for good; and `refused`, each body a target refused for good in the last day,
with its route, when, why and its file in `dead/`, kept across a restart. The relay judges
none of it: `jbus health` reads it and pages (`jbus.health`). jbus posts a `refresh` to
`blocking_url` each hour (`leftover.REFRESH_MINUTES`), so a relay it posts to hears a body at
least that often.

When Sous Chef is silent the relay pages a second way, the `pager` target (Home Assistant's
mobile push, `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE`), with `notify-send` beside
it. Silent is judged with no word from Sous Chef: (a) a POST on the `blocking` route that
failed pages each body that waits on that route, once for each event id; (b) an item still
open in a `reminder` or a `refresh` `PAGE_MINUTES` (45) after it began to block pages once
(`judge`). A POST to `/ack` naming an event id marks the items of that body seen, and a seen
item pages nothing under (b). A page is one line, and it goes through a spooled route of its
own, `page`, whose ids are kept for good.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import hmac
import http.server
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jbus import leftover, verbs

Body = dict[str, Any]
Say = Callable[[str], None]

REFUSED = 2
LIMIT = 1_000_000
PLACEHOLDER = "REPLACE_ME"
BLOCKING = {"gate", "stall", "alert", "waiting", "waiting-on-user"}
PASS = {"reminder", "refresh"}
AGAIN = {401, 403, 404, 407, 408, 429}
NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
SERVICE = re.compile(r"[a-z0-9_]{1,128}")
SECRET_URL = re.compile(r"\S+://\S*[@?]\S*?(?=[:,;)]?(\s|$))")
PAGE_MINUTES = leftover.REMIND_MINUTES + 30
SILENT_MINUTES = leftover.REFRESH_MINUTES + 30
BEAT_SECONDS = 60
REFUSED_KEPT = timedelta(days=1)
HEARTBEAT = "heartbeat.json"


def everything(body: Body) -> Body | None:
    return body


def blocking(body: Body) -> Body | None:
    """What blocks of a body: a reminder or a refresh whole, an `events` body of the second
    target whole when it has `items`, and of any other the events that are loud for the user
    or of a blocking kind. None when nothing in it blocks."""
    if str(body.get("kind") or body.get("event") or "") in PASS:
        return body
    events = [event for event in body.get("events") or [] if isinstance(event, dict)]
    if any(event.get("event") in PASS for event in events) or body.get("items"):
        return body
    kept = [e for e in events if e.get("loud") == "user" or e.get("event") in BLOCKING]
    if not kept:
        return None
    return {**body, "say": [e["say"] for e in kept if e.get("say")], "events": kept}


@dataclass(frozen=True)
class Target:
    name: str
    url: str
    key: str


def as_spooled(data: bytes) -> bytes:
    return data


def home_assistant(data: bytes) -> bytes:
    """A spooled page as Home Assistant's `notify` service takes it: its line, nothing else."""
    return json.dumps({"message": json.loads(data)["page"]}).encode()


@dataclass(frozen=True)
class Route:
    name: str
    target: str
    pick: Callable[[Body], Body | None]
    wire: Callable[[bytes], bytes] = as_spooled


TARGETS = {"sous-chef": ("GROK_WEBHOOK_URL", "GROK_WEBHOOK_KEY")}
PAGER = ("PAGER_HA_URL", "PAGER_HA_TOKEN", "PAGER_HA_SERVICE")
ROUTES = (
    Route("everything", "sous-chef", everything),
    Route("blocking", "sous-chef", blocking),
)
PAGES = Route("page", "pager", everything, home_assistant)


class Refused(Exception):
    """The relay's settings, which it does not start on."""


@dataclass(frozen=True)
class Settings:
    inbound: str
    targets: Mapping[str, Target]
    pager: Target
    port: int
    state: Path
    timeout: float
    retry: float
    dedup: float
    silent: float = SILENT_MINUTES


def _unusable(env: Mapping[str, str], key: str) -> str | None:
    if key not in env:
        return f"{key} is missing"
    if not env[key].strip():
        return f"{key} is empty"
    if PLACEHOLDER in env[key]:
        return f"{key} is {PLACEHOLDER}"
    return None


def settings(env: Mapping[str, str]) -> Settings:
    """The relay's settings from its environment. `Refused` names every key that is not
    usable, and no value."""
    wrong = [why for why in [_unusable(env, "RELAY_INBOUND_KEY")] if why]
    for name, keys in [*TARGETS.items(), (PAGES.target, PAGER)]:
        wrong += [f"target {name}: {why}" for key in keys if (why := _unusable(env, key))]
    if wrong:
        raise Refused("; ".join(wrong))
    for name, url in [*((name, url) for name, (url, _) in TARGETS.items()), ("pager", PAGER[0])]:
        if urllib.parse.urlsplit(env[url].strip()).scheme not in ("http", "https"):
            raise Refused(f"target {name}: {url} is not an http or https URL")
    base, token, service = (env[key].strip() for key in PAGER)
    if not SERVICE.fullmatch(service):
        raise Refused(f"target pager: {PAGER[2]} is not a notify service name")
    try:
        return Settings(
            inbound=env["RELAY_INBOUND_KEY"],
            targets={
                name: Target(name, env[url].strip(), env[key].strip())
                for name, (url, key) in TARGETS.items()
            },
            pager=Target("pager", f"{base.rstrip('/')}/api/services/notify/{service}", token),
            port=int(env.get("RELAY_PORT", "4390")),
            state=Path(env.get("RELAY_STATE", "~/.local/state/jbus-relay")).expanduser(),
            timeout=float(env.get("RELAY_TIMEOUT_SECONDS", "15")),
            retry=float(env.get("RELAY_RETRY_SECONDS", "300")),
            dedup=float(env.get("RELAY_DEDUP_SECONDS", "900")),
            silent=float(env.get("RELAY_SILENT_MINUTES", str(SILENT_MINUTES))),
        )
    except ValueError as error:
        numbers = "RELAY_PORT, RELAY_SILENT_MINUTES or a RELAY_*_SECONDS"
        raise Refused(f"{numbers}: {error}") from None


def event_id(body: Body) -> str:
    """The body's own `id` when it is a short name, else a hash of the body."""
    own = body.get("id")
    if isinstance(own, str) and NAME.fullmatch(own):
        return own
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()[:24]


class Failed(Exception):
    """A POST the target did not take. `final` when sending it again cannot help."""

    def __init__(self, why: str, final: bool = False) -> None:
        super().__init__(why)
        self.final = final


def post(target: Target, data: bytes, timeout: float) -> None:
    request = urllib.request.Request(
        target.url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {target.key}",
            "X-Automation-Key": target.key,
            "User-Agent": "jbus-relay",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            if not 200 <= answer.status < 300:
                raise Failed(f"HTTP {answer.status}")
    except urllib.error.HTTPError as error:
        final = 400 <= error.code < 500 and error.code not in AGAIN
        raise Failed(f"HTTP {error.code}", final) from None
    except Exception as error:
        why = str(getattr(error, "reason", error)) or type(error).__name__
        raise Failed(why.replace(target.url, "<url>").replace(target.key, "<key>")) from None


def _sync(folder: Path) -> None:
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Lane:
    """One route: its spool, the ids it sent, and the thread that posts the spool in order."""

    def __init__(
        self,
        route: Route,
        target: Target,
        config: Settings,
        say: Say,
        unheard: Callable[[str, Body], None] | None = None,
    ) -> None:
        self.route, self.target, self.config, self.say = route, target, config, say
        self.unheard = unheard
        self.spool = config.state / "spool" / route.name
        self.spool.mkdir(parents=True, exist_ok=True)
        for part in self.spool.glob("*.part"):
            part.unlink()
        self.dead = config.state / "dead" / route.name
        self.record = config.state / "sent" / route.name
        self.record.parent.mkdir(parents=True, exist_ok=True)
        self.sent = self._recent()
        part = self.record.with_suffix(".part")
        with part.open("w") as file:
            file.write("".join(f"{id} {at}\n" for id, at in self.sent.items()))
            file.flush()
            os.fsync(file.fileno())
        os.replace(part, self.record)
        _sync(self.record.parent)
        waiting = self._waiting()
        self.held = {self._id(path) for path in waiting}
        self.last = max((int(path.stem.split("-")[0]) for path in waiting), default=0)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.failing: Body | None = None
        self.changed: Callable[[], None] = lambda: None
        self.refused: Callable[[Body], None] = lambda one: None

    @staticmethod
    def _id(path: Path) -> str:
        return path.stem.split("-", 1)[-1]

    def _recent(self) -> dict[str, float]:
        """The ids sent within the dedup window, from `sent/<route>`, each with its time."""
        lines = self.record.read_text().splitlines() if self.record.exists() else []
        sent = {}
        for line in lines:
            id, _, at = line.partition(" ")
            with contextlib.suppress(ValueError):
                sent[id] = float(at)
        return {id: at for id, at in sent.items() if self._fresh(at)}

    def _fresh(self, at: float) -> bool:
        return time.time() - at < self.config.dedup

    def _waiting(self) -> list[Path]:
        return sorted(self.spool.glob("*.json"))

    def _done(self, path: Path, id: str, own: bool = False) -> None:
        """Write the id as sent, durably, before its file leaves the spool."""
        with self.lock:
            if not self._fresh(self.sent.get(id, 0.0)):
                at = math.inf if own else time.time()
                with self.record.open("a") as file:
                    file.write(f"{id} {at}\n")
                    file.flush()
                    os.fsync(file.fileno())
                self.sent[id] = at
            self.held.discard(id)
            path.unlink()

    def has(self, id: str) -> bool:
        """Whether the route holds the id, sent it, or had it refused for good."""
        with self.lock:
            if id in self.held or self._fresh(self.sent.get(id, 0.0)):
                return True
        return any(self.dead.glob(f"*-{id}.json"))

    def _silent(self, paths: list[Path]) -> None:
        """Tell `unheard` of each body that a failed POST leaves unsent."""
        if self.unheard is None:
            return
        for path in paths:
            with contextlib.suppress(FileNotFoundError, ValueError):
                self.unheard(self._id(path), json.loads(path.read_bytes()))

    def take(self, id: str, body: Body) -> bool:
        """Spool what the route picks of the body. False when it picks nothing or has the id."""
        picked = self.route.pick(body)
        if picked is None:
            return False
        with self.lock:
            if id in self.held or self._fresh(self.sent.get(id, 0.0)):
                self.say(f"relay: {self.route.name} has event {id} already, not sent again")
                return False
            data = json.dumps({**picked, "relay": {"id": id, "route": self.route.name}})
            self.last = max(time.time_ns(), self.last + 1)
            path = self.spool / f"{self.last:020d}-{id}.json"
            part = path.with_suffix(".part")
            with part.open("w") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(part, path)
            _sync(self.spool)
            self.held.add(id)
        self.wake.set()
        return True

    def drain(self) -> bool:
        """Post the spool in order. False at the first POST that failed, which stays."""
        for path in self._waiting():
            id = self._id(path)
            if self._fresh(self.sent.get(id, 0.0)):
                self._done(path, id)
                continue
            try:
                data = path.read_bytes()
                post(self.target, self.route.wire(data), self.config.timeout)
            except Failed as error:
                said = f"relay: POST to {self.target.name} ({self.route.name}) failed"
                said = f"{said} for event {id}"
                if not error.final:
                    since = (self.failing or {}).get("since") or _now()
                    was, self.failing = (
                        self.failing,
                        {
                            "route": self.route.name,
                            "since": since,
                            "why": str(error),
                        },
                    )
                    if was != self.failing:
                        self.changed()
                    self.say(f"{said}: {error}")
                    self._silent(self._waiting())
                    return False
                self._silent([path])
                self.dead.mkdir(parents=True, exist_ok=True)
                os.replace(path, self.dead / path.name)
                with self.lock:
                    self.held.discard(id)
                self.say(f"{said}: {error}, refused for good, kept in {self.dead / path.name}")
                if self.failing:
                    self.failing = None
                    self.changed()
                self.refused(
                    {"route": self.route.name, "at": _now(), "why": str(error), "file": path.name}
                )
                continue
            self._done(path, id, own=json.loads(data).get("id") == id)
            if self.failing:
                self.failing = None
                self.changed()
            self.say(f"relay: sent event {id} to {self.target.name} ({self.route.name})")
        return True

    def run(self) -> None:
        while True:
            self.wake.clear()
            try:
                went = self.drain()
            except Exception as error:
                self.say(f"relay: {self.route.name} could not read or clear its spool: {error!r}")
                went = False
            self.wake.wait(None if went else self.config.retry)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when if when.tzinfo else None


def page_line(project: str, line: str, minutes: float, event: str = "") -> str:
    """A page: the project, the line, how long it has blocked, and for (a) the event id. A
    URL that carries a key, as a query or a user, is cut out."""
    said = f"{project}: {SECRET_URL.sub('<url>', line)}, blocking {int(minutes)} min"
    return f"{said}, event {event}" if event else said


def unheard_line(id: str, body: Body) -> str | None:
    """The page for a body on the `blocking` route that Sous Chef did not take: its first
    item or event, and how many more. None for a body that names nothing, an all-clear."""
    at = _when(body.get("at"))
    named = []
    for one in [*(body.get("items") or []), *(body.get("events") or [])]:
        if isinstance(one, dict) and isinstance(one.get("line"), str):
            opened = _when(one.get("opened") or one.get("since"))
            minutes = (at - opened).total_seconds() / 60 if at and opened else 0
            project = one.get("project") or body.get("project") or "jbus"
            named.append((str(project), one["line"], max(minutes, 0)))
    if not named:
        return None
    project, line, minutes = named[0]
    more = f" and {len(named) - 1} more" if len(named) > 1 else ""
    return page_line(project, line + more, minutes, id)


@dataclass(frozen=True)
class Watch:
    """What the relay knows of what blocks: each item by its page id, a hash of its project,
    key and when it began to block (so an item that closes and opens again is a new one), the
    page ids marked seen, and the page ids each event id carried, for `/ack`."""

    items: dict[str, Body] = field(default_factory=dict)
    seen: frozenset[str] = frozenset()
    ids: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Watch:
        try:
            kept = json.loads(path.read_text())
            return cls(kept["items"], frozenset(kept["seen"]), kept["ids"])
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        part = path.with_suffix(".part")
        with part.open("w") as file:
            json.dump({"items": self.items, "seen": sorted(self.seen), "ids": self.ids}, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(part, path)


def page_id(project: str, key: str, opened: str) -> str:
    named = json.dumps([project, key, opened]).encode()
    return f"open-{hashlib.sha256(named).hexdigest()[:24]}"


def judge(watch: Watch, id: str, body: Body) -> tuple[Watch, list[tuple[str, str]]]:
    """What a body tells of what blocks, and the pages it makes, each `(page id, line)`.

    The items of an `events`, `reminder` or `refresh` body are kept, under the event id that
    carried them. A `refresh` lists every open item of its project, so the project's items it
    does not list closed: they are dropped. An item a `reminder` or `refresh` lists
    `PAGE_MINUTES` after it began to block (the body's `at` against the item's `opened`), and
    that is not seen, makes a page. The pager's route sends a page id once."""
    kind, project = body.get("kind"), body.get("project")
    if kind not in ("events", "reminder", "refresh"):
        return watch, []
    listed: dict[str, Body] = {}
    for one in body.get("items") or []:
        if not isinstance(one, dict):
            continue
        named, key, line = one.get("project") or project, one.get("key"), one.get("line")
        opened = one.get("opened") or one.get("since")
        if all(isinstance(value, str) for value in (named, key, line)) and _when(opened):
            item = {"project": named, "key": key, "line": line, "opened": opened}
            listed[page_id(named, key, opened)] = item
    items = watch.items | listed
    ids = {event: list(pages) for event, pages in watch.ids.items()}
    if listed:
        ids[id] = sorted(set(ids.get(id, [])) | set(listed))
    seen = watch.seen
    if kind == "refresh" and isinstance(project, str):
        closed = {page for page, one in items.items() if one["project"] == project} - set(listed)
        items = {page: one for page, one in items.items() if page not in closed}
        seen = seen - closed
        ids = {event: [p for p in pages if p not in closed] for event, pages in ids.items()}
        ids = {event: pages for event, pages in ids.items() if pages}
    pages = []
    at = _when(body.get("at"))
    if kind in ("reminder", "refresh") and at:
        for page, one in listed.items():
            minutes = (at - datetime.fromisoformat(one["opened"])).total_seconds() / 60
            if minutes >= PAGE_MINUTES and page not in seen:
                pages.append((page, page_line(one["project"], one["line"], minutes)))
    return Watch(items, seen, ids), pages


def notify(line: str, say: Say) -> None:
    """Raise the page on this machine's desktop. One that fails is said, and pages on."""
    command = shutil.which("notify-send")
    if command is None:
        say("relay: no notify-send on PATH, the page was not raised on the desktop")
        return
    try:
        done = subprocess.run(
            [command, "-u", "critical", "jbus page", line], capture_output=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        say(f"relay: notify-send failed: {error}")
        return
    if done.returncode:
        say(f"relay: notify-send failed with status {done.returncode}")


class Pager:
    """The second way: the `page` route to Home Assistant, and `notify-send` beside it."""

    def __init__(self, config: Settings, say: Say) -> None:
        self.say = say
        self.lane = Lane(PAGES, config.pager, config, say)

    def page(self, id: str, line: str) -> None:
        if self.lane.has(id) or not self.lane.take(id, {"id": id, "page": line}):
            return
        self.say(f"relay: paged {id}")
        threading.Thread(target=notify, args=(line, self.say), daemon=True).start()

    def unheard(self, id: str, body: Body) -> None:
        """(a): Sous Chef did not take a body that blocks."""
        line = unheard_line(id, body)
        if line is not None:
            self.page(f"unheard-{id}", line)


class Relay:
    def __init__(self, config: Settings, say: Say) -> None:
        self.config, self.say = config, say
        self.lock = threading.Lock()
        self.pager = Pager(config, say)
        self.lanes = [
            Lane(route, config.targets[route.target], config, say, self._unheard(route))
            for route in ROUTES
        ]
        self.watched = config.state / "watch.json"
        self.watch = Watch.load(self.watched)
        self.beating = config.state / HEARTBEAT
        try:
            heard = json.loads(self.beating.read_text()).get("heard")
        except (OSError, ValueError, AttributeError):
            heard = None
        self.heard: str | None = heard if _when(heard) else None
        self.refusals: list[Body] = self._refusals()
        self._failing()
        self.beat_lock = threading.Lock()
        self.started = _now()
        for lane in [*self.lanes, self.pager.lane]:
            lane.changed = self.beat
            lane.refused = self.refuse

    def _unheard(self, route: Route) -> Callable[[str, Body], None] | None:
        return self.pager.unheard if route.pick is blocking else None

    def take(self, body: Body) -> str:
        id = event_id(body)
        with self.lock:
            spooled = [lane.route.name for lane in self.lanes if lane.take(id, body)]
            watch, pages = judge(self.watch, id, body)
            if watch != self.watch:
                self.watch = watch
                self.watch.save(self.watched)
        self.heard = _now()
        self.beat()
        self.say(f"relay: took event {id}, spooled for {', '.join(spooled) or 'no route'}")
        for page, line in pages:
            self.pager.page(page, line)
        return id

    def ack(self, id: str) -> int | None:
        """Mark seen the items the event id carried. None for an id the relay does not hold."""
        with self.lock:
            pages = self.watch.ids.get(id)
            if pages is None:
                return None
            self.watch = Watch(self.watch.items, self.watch.seen | set(pages), self.watch.ids)
            self.watch.save(self.watched)
        self.say(f"relay: event {id} acknowledged, {len(pages)} item(s) seen")
        return len(pages)

    def _refusals(self) -> list[Body]:
        """The refusals the last heartbeat kept, of the last `REFUSED_KEPT`."""
        try:
            kept = json.loads(self.beating.read_text()).get("refused")
        except (OSError, ValueError, AttributeError):
            return []
        recent = []
        for one in kept if isinstance(kept, list) else []:
            at = _when(one.get("at")) if isinstance(one, dict) else None
            if at and datetime.now(UTC) - at < REFUSED_KEPT:
                recent.append(one)
        return recent

    def _failing(self) -> None:
        """Each route the last heartbeat names as failing, while it still holds a body: a
        restart does not end a failure, and it keeps the time it began."""
        try:
            kept = json.loads(self.beating.read_text()).get("failing")
        except (OSError, ValueError, AttributeError):
            return
        lanes = {lane.route.name: lane for lane in [*self.lanes, self.pager.lane]}
        for one in kept if isinstance(kept, list) else []:
            lane = lanes.get(one.get("route")) if isinstance(one, dict) else None
            if lane and _when(one.get("since")) and lane._waiting():
                lane.failing = {key: one.get(key) for key in ("route", "since", "why")}

    def refuse(self, one: Body) -> None:
        """A body was refused for good: keep it for the heartbeat, and beat."""
        self.refusals = [*self._recent(), one]
        self.beat()

    def _recent(self) -> list[Body]:
        now = datetime.now(UTC)
        return [one for one in self.refusals if now - _when(one["at"]) < REFUSED_KEPT]

    def beat(self) -> None:
        """Write the heartbeat: see the module. One that cannot be written is said."""
        failing = []
        for lane in [*self.lanes, self.pager.lane]:
            if lane.failing:
                failing.append({**lane.failing, "waiting": len(lane._waiting())})
        made = {
            "beat": _now(),
            "started": self.started,
            "heard": self.heard,
            "silent_minutes": self.config.silent,
            "failing": failing,
            "refused": self._recent(),
        }
        part = self.beating.with_suffix(".part")
        try:
            with self.beat_lock:
                part.write_text(json.dumps(made))
                os.replace(part, self.beating)
        except OSError as error:
            self.say(f"relay: could not write the heartbeat: {error}")

    def beats(self) -> None:
        while True:
            self.beat()
            time.sleep(BEAT_SECONDS)

    def start(self) -> None:
        for lane in [*self.lanes, self.pager.lane]:
            threading.Thread(target=lane.run, name=lane.route.name, daemon=True).start()
        threading.Thread(target=self.beats, name="heartbeat", daemon=True).start()

    def handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        relay = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self, code: int, said: Body | None = None) -> None:
                data = json.dumps(said or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                given = self.headers.get("X-Automation-Key") or ""
                if not hmac.compare_digest(given.encode(), relay.config.inbound.encode()):
                    relay.say("relay: refused a POST with the wrong key")
                    return self._answer(401)
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if not 0 < length:
                    relay.say("relay: refused a POST with no length")
                    return self._answer(400)
                if length > LIMIT:
                    relay.say(f"relay: refused a POST of {length} bytes")
                    return self._answer(413)
                try:
                    body = json.loads(self.rfile.read(length))
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    relay.say("relay: refused a POST that is not one JSON object")
                    return self._answer(400)
                if urllib.parse.urlsplit(self.path).path == "/ack":
                    return self._ack(body)
                try:
                    id = relay.take(body)
                except OSError as error:
                    relay.say(f"relay: could not spool event {event_id(body)}: {error}")
                    return self._answer(503)
                self._answer(202, {"id": id})

            def _ack(self, body: Body) -> None:
                id = body.get("id")
                if not isinstance(id, str) or not NAME.fullmatch(id):
                    relay.say("relay: refused an ack with no event id")
                    return self._answer(400)
                try:
                    seen = relay.ack(id)
                except OSError as error:
                    relay.say(f"relay: could not keep the ack of event {id}: {error}")
                    return self._answer(503)
                if seen is None:
                    relay.say(f"relay: an ack named event {id}, which holds no open item")
                    return self._answer(404)
                self._answer(200, {"id": id, "seen": seen})

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    def serve(self) -> None:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", self.config.port), self.handler())
        self.say(f"relay: listening on 127.0.0.1:{server.server_address[1]}")
        server.serve_forever()


def relay(env: Mapping[str, str] = os.environ, say: Say | None = None) -> int:
    say = say or functools.partial(print, flush=True)
    try:
        config = settings(env)
    except Refused as error:
        say(f"relay: refused to start: {error}")
        return REFUSED
    running = Relay(config, say)
    running.start()
    running.serve()
    return 0


VERBS = (
    verbs.Verb(
        "relay",
        "send what jbus posts on 127.0.0.1 on to Sous Chef, spooled, and page when it is silent",
        verbs.nothing,
        lambda args, config: relay(),
        config=False,
    ),
)
