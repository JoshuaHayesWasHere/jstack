"""`jbus health` takes one look at the machine the stack runs on. Every `jbus poll` takes the
same look, so jbus sees a failure that no thread runs into.

Each check returns a `Reading`: the number, what it counts, and the limit jbus compares it
with.

- `disk <mount>` and `inodes <mount>` are the space and the inodes used on each mount the
  stack writes to (jbus's state and homes, each project's checkout, the temp directory, the
  user's home, the ledger, the relay's state). Each is over its limit at `FULL` (80%) or
  more. A filesystem that counts no inodes (btrfs) has no inode number.
- `timeout jbus` and `timeout jmerge` count the passes systemd stopped at `jbus.service`'s
  TimeoutStartSec, and the runs of `jmerge` that a pass stopped at `JMERGE_TIMEOUT`. Both read the
  journal of `jbus.service` over the last `TIMEOUT_MINUTES`. A single one is an incident. A pass
  that systemd stopped cannot say so itself, so the journal is the one place that shows both.
- `relay`, `relay heartbeat`, `relay silent` and `relay errors` exist only where the config posts to
  the relay: a webhook on 127.0.0.1 or localhost, at `RELAY_PORT` of the relay's env file, which
  `jbus.service` does not load. Each is over its limit in one of these cases: the relay's unit is
  not active; its heartbeat is older than `BEAT_MINUTES`; the relay heard no body for the
  heartbeat's `silent_minutes`, `RELAY_SILENT_MINUTES` in the relay's env; a route's POSTs have
  failed for `ERRORS_MINUTES`; a target refused a body permanently in the last `REFUSED_MINUTES`.
  Such a body stays in the relay's `dead/` and the relay never sends it (`jbus.relay`). jbus does
  not judge silence and errors from a heartbeat that is stale.
- `quota <instance> <window>` and `capped <instance>` cover each instance of the role map's pools
  and the built-in one. They read the ledger (`jroles.ledger`), which gets its entries from the
  threads' status lines and from their limit failures. jbus pages for the seven-day window at
  `FULL`. The five-hour window fills and resets each day, so jbus pages for it only when it is full.
  A `capped` reading is over while `jroles.pool.choose` skips its instance. While the cap lasts, new
  launches go to the next instance of the pool, and with every instance capped no launch starts. The
  cap ends by itself at the reset, and its recovered line says that launches on the instance resume.

A reading over its limit is an incident, with the key `health <the reading's key>`, which
`jbus.alert` keeps as a streak. jbus pages it once when it starts (`alert.opened`), and once
when a reading under the limit ends it (`alert.closed`). When jbus could not take a reading
(`over` None), it leaves that reading's incident as it is. When jbus no longer takes an
incident's reading, because a mount or an instance is gone or the config no longer posts to
a relay, jbus ends the incident with no line. jbus sends a page to the desk, and once to
the top-level webhook as an event of the machine (`wake.Box.send`).

`jbus poll` pages. Its look is the first step of the config's first project (rank 6 of
`before-watch`, ahead of every other step), so the look runs in every pass before another
step can raise. It also runs before the launch, so a capped instance's lines come before the
launch that skips the instance or goes back to it. When the look raises, the pass says so
and goes on. `jbus health` prints every reading and pages nothing.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import tempfile
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
import jroles
import jsettings
from jbus import alert, read_json, verbs, wake
from jbus import relay as relaying
from jroles import ledger, pool

FULL = 80
TIMEOUT_MINUTES = 60
BEAT_MINUTES = 3
ERRORS_MINUTES = 10
REFUSED_MINUTES = 60
PREFIX = "health "
RELAY = "jbus-relay.service"
UNIT = "jbus.service"
LOCAL = {"127.0.0.1", "localhost", "::1"}
TIMED_OUT = "Failed with result 'timeout'"
JMERGE_TIMED_OUT = "jmerge did not run (Command "
GIB = 2**30


@dataclass(frozen=True)
class Mount:
    """A `Mount` is a mount the stack writes. It holds the bytes used and the bytes still free
    to a user, and the inodes used and the inodes in all. The two inode counts are 0 on a
    filesystem that does not count inodes."""

    point: str
    used: int
    free: int
    inodes_used: int
    inodes: int


@dataclass(frozen=True)
class Relay:
    """A `Relay` is what the relay shows. `state` is its unit's state, and `beat` is its
    heartbeat, or None when the relay has none."""

    state: str
    beat: dict[str, Any] | None
    path: Path


@dataclass(frozen=True)
class Machine:
    """A `Machine` is one look, as `gather` reads it from the system. `journal` is None where
    `gather` could not read it."""

    mounts: tuple[Mount, ...] = ()
    journal: tuple[str, ...] | None = ()
    start_timeout: str = ""
    relay: Relay | None = None
    kept: ledger.Ledger = field(default_factory=dict)
    instances: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reading:
    """A `Reading` is one check's number. `said` is the number and what it counts, and `limit`
    is what jbus compares it with. `over` is whether the number is past the limit, or None
    where jbus could not read it. `then` is what follows while the reading is over, and
    `after` is what follows once it is not."""

    key: str
    said: str
    limit: str
    over: bool | None
    then: str = ""
    after: str = ""

    def line(self, recovered: bool = False) -> str:
        follows = self.after if recovered else self.then if self.over else ""
        return f"{PREFIX}{self.key}: {self.said}, {self.limit}" + (
            f"; {follows}" if follows else ""
        )


class Senses:
    """`Senses` reads the machine for `gather`. A test passes its own `Senses`."""

    def mounts(self, paths: Iterable[Path]) -> list[Mount]:
        """Return the mount of each path, once each, by its mount point."""
        found: dict[str, Mount] = {}
        for path in paths:
            while not path.exists() and path != path.parent:
                path = path.parent
            point = _point(path)
            if point in found:
                continue
            try:
                got = os.statvfs(point)
            except OSError:
                continue
            used = (got.f_blocks - got.f_bfree) * got.f_frsize
            found[point] = Mount(
                point, used, got.f_bavail * got.f_frsize, got.f_files - got.f_ffree, got.f_files
            )
        return list(found.values())

    def journal(self, unit: str, minutes: int) -> list[str] | None:
        return _lines(
            ["journalctl", "--user", "-u", unit, "--since", f"-{minutes}min", "-o", "cat"]
        )

    def show(self, unit: str, name: str) -> str:
        said = _lines(["systemctl", "--user", "show", unit, "-p", name, "--value"])
        return said[0].strip() if said else ""


def _point(path: Path) -> str:
    path = path.resolve()
    while path != path.parent and path.parent.stat().st_dev == path.stat().st_dev:
        path = path.parent
    return str(path)


def _lines(command: list[str]) -> list[str] | None:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.splitlines() if done.returncode == 0 else None


SENSES = Senses()


def clock() -> datetime:
    """Return the time at which `jbus health` takes its look."""
    return datetime.now(UTC)


def relay_env() -> Path:
    """Return the relay's settings file, which `jbus-relay.service` loads and `jbus.service`
    does not."""
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "jbus-relay" / "env"


def relay_setting(name: str, default: str) -> str:
    """Read one of the relay's settings as the relay reads it: the line of its env file, else
    this process's environment, else the relay's default. It keeps no other line of the file,
    since the file holds the relay's keys."""
    return relaying.env_file(relay_env()).get(name) or os.environ.get(name) or default


def relay_state() -> Path:
    """Return where the relay keeps its state, `RELAY_STATE`."""
    return Path(relay_setting("RELAY_STATE", "~/.local/state/jbus-relay")).expanduser()


def posts_to_relay(config: jbus.Config) -> bool:
    """Return whether the config posts to the relay: a webhook on this machine at its port,
    `RELAY_PORT` (4390), that a project's `wake` posts to, or the second target."""
    try:
        port = int(relay_setting("RELAY_PORT", "4390"))
    except ValueError:
        port = 4390
    posting = [project for project in config.projects if project.to_webhook]
    urls = [project.webhook_url for project in posting]
    urls += [config.webhook[0] if posting else "", config.blocking[0]]
    found = (urllib.parse.urlsplit(url) for url in urls if url)
    return any(one.hostname in LOCAL and one.port == port for one in found)


def instances(say: Callable[[str], None]) -> tuple[str, ...]:
    """Return the built-in instance and every instance a role's pool names."""
    found = [ledger.BUILT_IN]
    for role in jroles.ROLES:
        try:
            found += [one for chosen in pool.selections(role) for one in chosen.instances]
        except jroles.Refused as error:
            say(f"health: the role map gives {role} no pool ({error})")
    return tuple(dict.fromkeys(found))


def gather(
    config: jbus.Config, now: datetime, say: Callable[[str], None], senses: Senses
) -> Machine:
    """Read the machine's state once, through `senses`."""
    wired = posts_to_relay(config)
    paths = [config.state_dir, config.home_dir, *(p.checkout for p in config.projects)]
    paths += [Path(tempfile.gettempdir()), Path.home(), ledger.path().parent]
    relay = None
    if wired:
        where = relay_state()
        paths.append(where)
        beat = read_json(where / "heartbeat.json", None)
        relay = Relay(
            senses.show(RELAY, "ActiveState"), beat if isinstance(beat, dict) else None, where
        )
    journal = senses.journal(UNIT, TIMEOUT_MINUTES)
    named = instances(say)
    return Machine(
        mounts=tuple(senses.mounts(paths)),
        journal=None if journal is None else tuple(journal),
        start_timeout=senses.show(UNIT, "TimeoutStartUSec"),
        relay=relay,
        kept=ledger.read(named),
        instances=named,
    )


def _share(used: int, whole: int) -> int:
    """Return a share in whole percent, rounded up, as `df` shows it."""
    return math.ceil(used * 100 / whole) if whole else 0


def disks(mounts: Iterable[Mount]) -> list[Reading]:
    found = []
    for one in mounts:
        size = one.used + one.free
        share = _share(one.used, size)
        said = f"{share}% of its space used ({one.used / GIB:.1f} of {size / GIB:.1f} GiB)"
        found.append(Reading(f"disk {one.point}", said, f"alerts at {FULL}%", share >= FULL))
        if not one.inodes:
            continue
        share = _share(one.inodes_used, one.inodes)
        said = f"{share}% of its inodes used ({one.inodes_used:,} of {one.inodes:,})"
        found.append(Reading(f"inodes {one.point}", said, f"alerts at {FULL}%", share >= FULL))
    return found


def timeouts(journal: tuple[str, ...] | None, start_timeout: str) -> list[Reading]:
    window = f"in the last {TIMEOUT_MINUTES} min"
    limit = "alerts at 1"
    if journal is None:
        said = f"the journal of {UNIT} could not be read"
        return [Reading(f"timeout {name}", said, limit, None) for name in ("jbus", "jmerge")]
    passes = sum(TIMED_OUT in line for line in journal)
    runs = sum(JMERGE_TIMED_OUT in line and "timed out after" in line for line in journal)
    unit = f"its {start_timeout} start timeout" if start_timeout else "its start timeout"
    jmerge = f"its {wake.JMERGE_TIMEOUT // 60} min timeout"
    return [
        Reading(
            "timeout jbus", f"{UNIT} stopped at {unit} {passes} times {window}", limit, passes > 0
        ),
        Reading(
            "timeout jmerge", f"jmerge stopped at {jmerge} {runs} times {window}", limit, runs > 0
        ),
    ]


def _minutes(since: Any, now: datetime) -> int | None:
    try:
        at = datetime.fromisoformat(str(since))
    except ValueError:
        return None
    return int((now - at).total_seconds() // 60) if at.tzinfo else None


def relays(relay: Relay | None, now: datetime) -> list[Reading]:
    """Return the relay's readings. jbus counts silence from the last body the relay heard,
    and a restart does not reset that time. `started` counts only for a relay that has never
    heard a body, so a relay that restarts often still reads as silent."""
    if relay is None:
        return [Reading("relay", "the config posts nothing to 127.0.0.1", "not watched", False)]
    found = [
        Reading(
            "relay",
            f"{RELAY} is {relay.state or 'not known'}",
            "alerts when it is not active",
            None if not relay.state else relay.state != "active",
        )
    ]
    beat = relay.beat or {}
    age = _minutes(beat.get("beat"), now)
    limit = f"alerts after {BEAT_MINUTES} min"
    if age is None:
        said = f"no heartbeat in {relay.path / 'heartbeat.json'}"
        found.append(Reading("relay heartbeat", said, limit, True))
    else:
        said = f"last heartbeat {age} min ago"
        found.append(Reading("relay heartbeat", said, limit, age >= BEAT_MINUTES))
    live = relay.state == "active" and age is not None and age < BEAT_MINUTES
    silent = beat.get("silent_minutes")
    quiet = _minutes(beat.get("heard") or beat.get("started"), now)
    if isinstance(silent, (int, float)) and quiet is not None:
        said = f"no body heard for {quiet} min"
        limit = f"alerts after {silent:g} min (RELAY_SILENT_MINUTES)"
        found.append(Reading("relay silent", said, limit, quiet >= silent if live else None))
    failing = [one for one in beat.get("failing") or [] if isinstance(one, dict)]
    ages = [(_minutes(one.get("since"), now) or 0, one) for one in failing]
    long = [(minutes, one) for minutes, one in ages if minutes >= ERRORS_MINUTES]
    limit = f"alerts when a route's POSTs fail for {ERRORS_MINUTES} min"
    if long:
        minutes, one = max(long, key=lambda pair: pair[0])
        said = (
            f"POSTs on route {one.get('route')} failing for {minutes} min ({one.get('why')}), "
            f"{one.get('waiting', 0)} bodies wait"
        )
    else:
        said = f"{len(failing)} routes failing"
    found.append(Reading("relay errors", said, limit, bool(long) if live else None))
    refused = [one for one in beat.get("refused") or [] if isinstance(one, dict)]
    ages = [(m, one) for one in refused if (m := _minutes(one.get("at"), now)) is not None]
    lately = [(m, one) for m, one in ages if m < REFUSED_MINUTES]
    limit = f"alerts at 1 in the last {REFUSED_MINUTES} min"
    said = f"{len(lately)} bodies refused for good in the last {REFUSED_MINUTES} min"
    if lately:
        minutes, last = min(lately, key=lambda pair: pair[0])
        said += (
            f", the last {minutes} min ago on route {last.get('route')} ({last.get('why')}), "
            f"kept in {relay.path / 'dead' / str(last.get('route')) / str(last.get('file'))}"
        )
    if relay.beat is None:
        said = f"no heartbeat in {relay.path / 'heartbeat.json'} to read the refusals of"
    found.append(
        Reading("relay refused", said, limit, None if relay.beat is None else bool(lately))
    )
    return found


def quotas(
    kept: ledger.Ledger, named: tuple[str, ...], now: datetime, user: jsettings.Settings
) -> list[Reading]:
    found = []
    capped = {one: ledger.capped_until(kept, one, now) for one in named}
    every = all(capped.values())
    for one in named:
        records = sorted((r for (i, _), r in kept.items() if i == one), key=lambda r: r.window)
        if not records:
            continue
        for record in records:
            resets = datetime.fromtimestamp(record.resets, UTC)
            weekly = record.window == "seven_day"
            if resets <= now:
                said = f"the {record.window} window reset {user.stamp(resets)}"
                over = False
            else:
                used = f"{record.used:g}% of the {record.window} window used"
                said = f"{used}, resets {user.stamp(resets)}"
                over = record.used >= FULL if weekly else False
            limit = f"alerts at {FULL}%" if weekly else f"paged when full, as capped {one}"
            found.append(Reading(f"quota {one} {record.window}", said, limit, over))
        until = capped[one]
        full = [r.window for r in records if r.full(now)]
        if until is None:
            said, then = "no window full", ""
        else:
            said = f"{' and '.join(full)} full until {user.stamp(until)}"
            then = f"launches skip {one} until then"
            if every:
                first = min(at for at in capped.values() if at)
                then += (
                    f"; every instance is capped, and no launch starts before {user.stamp(first)}"
                )
        after = f"launches on {one} resume"
        limit = "pauses its launches at 100% of a window"
        found.append(Reading(f"capped {one}", said, limit, until is not None, then, after))
    return found


def readings(machine: Machine, now: datetime, user: jsettings.Settings) -> list[Reading]:
    """Return every check of one look, in the order `jbus health` prints them."""
    return [
        *disks(machine.mounts),
        *timeouts(machine.journal, machine.start_timeout),
        *relays(machine.relay, now),
        *quotas(machine.kept, machine.instances, now, user),
    ]


def look(
    config: jbus.Config, now: datetime, say: Callable[[str], None], senses: Senses | None = None
) -> list[Reading]:
    return readings(gather(config, now, say, senses or SENSES), now, config.user)


def watch(config: jbus.Config, now: datetime, say: Callable[[str], None]) -> list[Reading]:
    """Take a look, and page each incident that starts or ends: see the module."""
    found = look(config, now, say)
    state = config.state_dir
    taken = {PREFIX + one.key: one for one in found}
    owed = []
    for key, one in taken.items():
        if one.over:
            line = alert.opened(state, key, one.line(), now=now)
        elif one.over is False:
            line = alert.closed(state, key, one.line(recovered=True), user=config.user)
        else:
            line = None
        if line:
            owed.append((key, line))
    for key in alert.streaks(state):
        if key.startswith(PREFIX) and key not in taken:
            alert.retire(state, key)
    for key, line in owed:
        page(config, now, say, line)
        alert.told(state, key)
    return found


def first(half: Any) -> None:
    """Take the look of a pass, in the first step of the config's first project: see the module."""
    run = half.run
    if run.project != run.config.projects[0]:
        return
    try:
        watch(run.config, run.now, run.say)
    except Exception as error:
        run.say(f"health failed: {alert.why(error, *run.config.hooks())}")


def page(config: jbus.Config, now: datetime, say: Callable[[str], None], line: str) -> None:
    """Say the line, raise it on the desk, and queue it once for the top-level webhook."""
    say(line)
    wake.notify(line)
    if config.projects:
        first = config.projects[0]
        alert.queue(wake.Box(config.state(first), first, config.webhook), line, machine=True)


def show(found: list[Reading]) -> list[str]:
    marks = {True: "over", False: "ok", None: "?"}
    return [f"{marks[one.over]:<4} {one.line()}" for one in found]


def run_health(args: argparse.Namespace, config: jbus.Config) -> int:
    """Print every reading, and return 1 when a reading is over its limit."""
    found = look(config, clock(), print)
    for line in show(found):
        print(line)
    return 1 if any(one.over for one in found) else 0


STEPS = (verbs.Step("before-watch", 6, "health.first", first),)
VERBS = (
    verbs.Verb(
        "health",
        "check disk, timeouts, the relay and the usage quota: each number and its limit",
        verbs.nothing,
        run_health,
    ),
)
