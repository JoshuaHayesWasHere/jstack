"""`jbus relay`: take what jbus posts on 127.0.0.1 and send it on to Sous Chef, never dropping
a body without a line in the journal.

The relay listens on `RELAY_PORT` (4390) of 127.0.0.1 and takes a POST whose
`X-Automation-Key` is `RELAY_INBOUND_KEY` and whose body is one JSON object. Each body it
takes has an id: the body's own `id` when that is a short name, else a hash of the body, so a
body posted twice has one id. Each route of `ROUTES` picks what it sends of the body, and the
picked body, with `relay: {"id", "route"}` beside its keys, is written to the route's spool
before the relay answers 202. A route's sender thread posts its spool in order, off the
request path and with a timeout, so a webhook that is slow or down never holds back the next
body. A body it posted is put in the route's `sent` file and taken out of the spool; one that
failed stays, the journal gets `relay: POST to <target> (<route>) failed for event <id>: <why>`,
and it goes again after `RELAY_RETRY_SECONDS` or when the next body comes. One the target
refuses as a request (a 4xx but 408 and 429) would never go: it moves to `dead/<route>/`, with
a line, so the bodies behind it go on. An id a route
already sent or holds is not spooled again. A POST taken and not yet in `sent` when the relay
stops goes once more after its start: the relay sends at least once, and never twice for an id
it wrote as sent.

Both routes go to the one target, Sous Chef (`GROK_WEBHOOK_URL`, `GROK_WEBHOOK_KEY`):
`everything`, every body as it came, and `blocking`, what blocks (`blocking`). A target whose
URL or key is missing, empty or REPLACE_ME, or a missing inbound key, is refused at start: the
relay names each such key in the journal, never its value, and exits 2, which
`jbus-relay.service` does not restart. State is in `RELAY_STATE`, ~/.local/state/jbus-relay:
`spool/<route>/`, `sent/<route>` and `dead/<route>/`.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import hmac
import http.server
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jbus import verbs

Body = dict[str, Any]
Say = Callable[[str], None]

REFUSED = 2
LIMIT = 1_000_000
PLACEHOLDER = "REPLACE_ME"
BLOCKING = {"gate", "stall", "alert", "waiting", "waiting-on-user"}
PASS = {"reminder", "refresh"}
NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")


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


@dataclass(frozen=True)
class Route:
    name: str
    target: str
    pick: Callable[[Body], Body | None]


TARGETS = {"sous-chef": ("GROK_WEBHOOK_URL", "GROK_WEBHOOK_KEY")}
ROUTES = (
    Route("everything", "sous-chef", everything),
    Route("blocking", "sous-chef", blocking),
)


class Refused(Exception):
    """The relay's settings, which it does not start on."""


@dataclass(frozen=True)
class Settings:
    inbound: str
    targets: Mapping[str, Target]
    port: int
    state: Path
    timeout: float
    retry: float


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
    for name, keys in TARGETS.items():
        wrong += [f"target {name}: {why}" for key in keys if (why := _unusable(env, key))]
    if wrong:
        raise Refused("; ".join(wrong))
    for name, (url, _) in TARGETS.items():
        if urllib.parse.urlsplit(env[url].strip()).scheme not in ("http", "https"):
            raise Refused(f"target {name}: {url} is not an http or https URL")
    try:
        return Settings(
            inbound=env["RELAY_INBOUND_KEY"],
            targets={
                name: Target(name, env[url].strip(), env[key].strip())
                for name, (url, key) in TARGETS.items()
            },
            port=int(env.get("RELAY_PORT", "4390")),
            state=Path(env.get("RELAY_STATE", "~/.local/state/jbus-relay")).expanduser(),
            timeout=float(env.get("RELAY_TIMEOUT_SECONDS", "15")),
            retry=float(env.get("RELAY_RETRY_SECONDS", "300")),
        )
    except ValueError as error:
        numbers = "RELAY_PORT, RELAY_TIMEOUT_SECONDS or RELAY_RETRY_SECONDS"
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
        final = 400 <= error.code < 500 and error.code not in (408, 429)
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

    def __init__(self, route: Route, target: Target, config: Settings, say: Say) -> None:
        self.route, self.target, self.config, self.say = route, target, config, say
        self.spool = config.state / "spool" / route.name
        self.spool.mkdir(parents=True, exist_ok=True)
        for part in self.spool.glob("*.part"):
            part.unlink()
        self.dead = config.state / "dead" / route.name
        self.record = config.state / "sent" / route.name
        self.record.parent.mkdir(parents=True, exist_ok=True)
        self.sent = set(self.record.read_text().split()) if self.record.exists() else set()
        waiting = self._waiting()
        self.held = {self._id(path) for path in waiting}
        self.last = max((int(path.stem.split("-")[0]) for path in waiting), default=0)
        self.lock = threading.Lock()
        self.wake = threading.Event()

    @staticmethod
    def _id(path: Path) -> str:
        return path.stem.split("-", 1)[-1]

    def _waiting(self) -> list[Path]:
        return sorted(self.spool.glob("*.json"))

    def _done(self, path: Path, id: str) -> None:
        """Write the id as sent, durably, before its file leaves the spool."""
        with self.lock:
            if id not in self.sent:
                with self.record.open("a") as file:
                    file.write(f"{id}\n")
                    file.flush()
                    os.fsync(file.fileno())
                self.sent.add(id)
            self.held.discard(id)
            path.unlink()

    def take(self, id: str, body: Body) -> bool:
        """Spool what the route picks of the body. False when it picks nothing or has the id."""
        picked = self.route.pick(body)
        if picked is None:
            return False
        with self.lock:
            if id in self.sent or id in self.held:
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
            if id in self.sent:
                self._done(path, id)
                continue
            try:
                post(self.target, path.read_bytes(), self.config.timeout)
            except Failed as error:
                said = f"relay: POST to {self.target.name} ({self.route.name}) failed"
                said = f"{said} for event {id}"
                if not error.final:
                    self.say(f"{said}: {error}")
                    return False
                self.dead.mkdir(parents=True, exist_ok=True)
                os.replace(path, self.dead / path.name)
                with self.lock:
                    self.held.discard(id)
                self.say(f"{said}: {error}, refused for good, kept in {self.dead / path.name}")
                continue
            self._done(path, id)
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


class Relay:
    def __init__(self, config: Settings, say: Say) -> None:
        self.config, self.say = config, say
        self.lock = threading.Lock()
        self.lanes = [Lane(route, config.targets[route.target], config, say) for route in ROUTES]

    def take(self, body: Body) -> str:
        id = event_id(body)
        with self.lock:
            spooled = [lane.route.name for lane in self.lanes if lane.take(id, body)]
        self.say(f"relay: took event {id}, spooled for {', '.join(spooled) or 'no route'}")
        return id

    def start(self) -> None:
        for lane in self.lanes:
            threading.Thread(target=lane.run, name=lane.route.name, daemon=True).start()

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
                try:
                    id = relay.take(body)
                except OSError as error:
                    relay.say(f"relay: could not spool event {event_id(body)}: {error}")
                    return self._answer(503)
                self._answer(202, {"id": id})

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    def serve(self) -> None:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", self.config.port), self.handler())
        self.say(f"relay: listening on 127.0.0.1:{self.config.port}")
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


def _arguments(shown: argparse.ArgumentParser) -> None:
    pass


VERBS = (
    verbs.Verb(
        "relay",
        "send what jbus posts on 127.0.0.1 on to Sous Chef, spooled",
        _arguments,
        lambda args, config: relay(),
        config=False,
    ),
)
