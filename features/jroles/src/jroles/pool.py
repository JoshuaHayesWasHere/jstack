"""Which instance of a role's pool a launch or a move goes to.

A role line names its pool in order (`crew: claudeAgent claude-opus-5-5
claudeAgent,claudeAgent_claude_prime`). `choose` takes the first instance of the pool with
headroom in the ledger (`jroles.ledger`). It skips an instance only while one of its windows is
full and has not reset. For a new launch, jroles counts a window full at the user's `headroom`
(`jsettings`, 90 by default). For a move off a running thread (`jbus.failover`), jbus counts it
full only at a real cap, 100. So every launch goes to the first account until that account nears its
cap, and a thread stays on the account it started on until that account is capped. No launch
rotates through the pool. When every instance is full, the choice names no instance, and gives
the time when the first instance resets.

To grow the pool, add the instance in T3 Code's settings (`providerInstances`, which
`jroles.inventory` reads) and one more id to the role line. `jroles` refuses a line with an id
that T3 does not list under the line's provider, so a Claude pool never names a Codex or a
Cursor instance. When T3 has no settings file, `jroles` takes the line as the user wrote it.

Three more reads go with that choice. `lone` says which role has a pool of one while T3 lists
another instance of its provider, for `jroles --check` and the doctor. `unread` says when a Claude
instance's ledger is no fresh reading: such an instance counts as usable, since a blind account
beats a stopped bus, and whoever chooses it says so. `held` gives the pools that hold the bus now,
with every instance capped, for `jbus status` and the home's one alert.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jsettings
from jroles import ROLES, Refused, Selection, inventory, ledger, read_map

WAIT = 75


@dataclass(frozen=True)
class Choice:
    """Where a launch or a move goes, and why it is not the pool's first instance. `instance`
    is None while every instance is capped or named by `skip`. `until` is then the first
    reset, or None when no instance is capped. `passed` holds each instance that `choose`
    skipped because `skip` named it."""

    instance: str | None
    why: str
    until: datetime | None = None
    passed: tuple[str, ...] = ()


def choose(
    pool: tuple[str, ...],
    kept: ledger.Ledger,
    now: datetime,
    skip: Mapping[str, str] | None = None,
    full: float = ledger.FULL,
) -> Choice:
    """The first instance of `pool` with headroom in `kept`, which means none of its windows
    is used to `full` or more. The function skips each instance that `skip` names, for the
    reason `skip` gives (`jbus` skips an instance that is not mirrored). When `skip` names
    every instance, there is no instance and no reset to wait for."""
    skip = skip or {}
    capped, passed = [], tuple(instance for instance in pool if instance in skip)
    told = [skip[instance] for instance in passed]
    for instance in pool:
        if instance in skip:
            continue
        until = ledger.capped_until(kept, instance, now, full)
        if until is None:
            whys = [f"{name} is capped until {at.isoformat()}" for name, at in capped]
            return Choice(instance, "; ".join([*whys, *told]), passed=passed)
        capped.append((instance, until))
    if passed:
        whys = [f"{name} is capped until {at.isoformat()}" for name, at in capped]
        first = min((until for _, until in capped), default=None)
        return Choice(None, "; ".join([*whys, *told]), first, passed)
    first = min(until for _, until in capped)
    names = [name for name, _ in capped]
    if len(names) == 1:
        return Choice(None, f"{names[0]} is capped until {first.isoformat()}", first)
    every = "both" if len(names) == 2 else "all"
    listed = f"{', '.join(names[:-1])} and {names[-1]}"
    return Choice(None, f"{listed} are {every} capped until {first.isoformat()}", first)


def check(role: str, selection: Selection, drivers: dict[str, str] | None) -> None:
    """Refuse a pool that names an instance T3 does not list under the line's provider. The
    provider's built-in instance needs no line in T3's list. `drivers` of None means T3 has no
    settings file."""
    if drivers is None:
        return
    for instance in selection.pool:
        if instance != selection.provider and drivers.get(instance) != selection.provider:
            raise Refused(
                f"refused {role}: {instance} is no {selection.provider} instance of T3's settings"
            )


@dataclass(frozen=True)
class Route:
    """A role's selection, and the instance of its pool that `choose` picked from the
    ledger."""

    selection: Selection
    choice: Choice

    def as_json(self) -> dict[str, object]:
        return self.selection.as_json(self.choice.instance)


def selections(role: str) -> tuple[Selection, ...]:
    """The role's lines of the map, in order, with each pool checked against the inventory,
    or none when the role inherits. Only `review` has more than one line. The function refuses
    a map or T3 settings that it cannot use."""
    where = jsettings.config_home()
    try:
        text = (where / "roles").read_text()
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "it is not UTF-8"
        raise Refused(f"cannot read {where / 'roles'}: {reason}") from error
    chosen = read_map(text, role)
    if not chosen:
        return ()
    settings = inventory.path()
    listed = inventory.declared(settings, Path.home()) if settings.exists() else None
    if isinstance(listed, str):
        raise Refused(f"refused {role}: {settings}: {listed}")
    drivers = None if listed is None else {name: each.driver for name, each in listed.items()}
    for one in chosen:
        check(role, one, drivers)
    return chosen


def routes(role: str, now: datetime) -> tuple[Route, ...]:
    """Where each launch of `role` goes now, one for each of its lines, or none when the role
    inherits. An instance is full at the user's headroom. The function refuses settings that
    it cannot use."""
    chosen = selections(role)
    if not chosen:
        return ()
    full = headroom(role)
    return tuple(
        Route(one, choose(one.instances, ledger.read(one.instances), now, full=full))
        for one in chosen
    )


def headroom(role: str) -> float:
    """The user's `headroom`, which is the share at which jroles counts an instance full for a
    new launch of `role`. The function refuses settings that it cannot use."""
    try:
        return jsettings.load().headroom
    except jsettings.Invalid as error:
        raise Refused(f"refused {role}: {error}") from error


def lone(text: str, listed: Mapping[str, inventory.Instance]) -> list[str]:
    """One line for each line of the map `text` whose pool has one instance while `listed`, T3's
    instances, has another enabled one of its provider: a cap on it stops the role with the other
    account free. Each line gives the fix, the map's line with the others added. Infra owns the map,
    so the fix is theirs to make. The function raises `Refused` for a map it cannot read."""
    found = []
    for role in ROLES:
        for one in read_map(text, role):
            others = [
                name
                for name, each in listed.items()
                if each.driver == one.provider and each.enabled and name not in one.instances
            ]
            if len(one.instances) == 1 and others:
                found.append(
                    f"{role} has one instance, {one.instances[0]}, while T3's settings also list "
                    f"{', '.join(others)}: a cap on it stops the role with the other account free. "
                    f"Send infra the fix for the role map: {_line(role, one, others)}"
                )
    return found


def _line(role: str, one: Selection, others: list[str]) -> str:
    """The map's line for `one`, with `others` added to its pool."""
    words = [one.provider, one.model, ",".join([*one.instances, *others])]
    if one.effort is not None:
        words.append(f"effort={one.effort}")
    if one.fast is not None:
        words.append(f"fast={'on' if one.fast else 'off'}")
    return f"{role}: {' '.join(words)}"


def problems() -> list[str]:
    """What `jroles --check` reports: the map's pools of one (`lone`), or why it cannot tell."""
    where = jsettings.config_home() / "roles"
    try:
        text = where.read_text()
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError):
        return [f"{where} cannot be read"]
    settings = inventory.path()
    listed = inventory.declared(settings, Path.home())
    if isinstance(listed, str):
        return [f"{settings}: {listed}"]
    return lone(text, listed)


def unread(instance: str, now: datetime) -> str:
    """Why nobody can read a Claude instance's use now, as a line that says it counts as usable, or
    nothing while its ledger is fresh. `jgauge limits` reads only Claude homes, so another
    provider's ledger holds only its caps, and being old says nothing of it."""
    listed = inventory.declared(inventory.path(), Path.home())
    known = inventory.claude_instances({} if isinstance(listed, str) else listed, Path.home())
    why = ledger.stale(ledger.file_of(instance), now) if instance in known else None
    if why is None:
        return ""
    return f"{instance}'s ledger is no fresh reading ({why}): its use is unread, and it counts as usable"


@dataclass(frozen=True)
class Held:
    """A pool with every instance full: the roles on it, its instances, the first reset, and why."""

    roles: tuple[str, ...]
    instances: tuple[str, ...]
    until: datetime
    why: str

    def as_json(self) -> dict[str, object]:
        return {
            "roles": list(self.roles),
            "instances": list(self.instances),
            "until": self.until.isoformat(),
            "why": self.why,
        }


def held(now: datetime) -> list[Held]:
    """The pools with no instance for a launch now, each once, whichever roles and order name its
    instances. A role whose map or settings cannot be used holds nothing here: `jbus health` and the
    launch say so."""
    found: dict[frozenset[str], Held] = {}
    for role in ROLES:
        try:
            routed = routes(role, now)
        except Refused:
            continue
        for one in routed:
            if one.choice.instance is not None or one.choice.until is None:
                continue
            key = frozenset(one.selection.instances)
            was = found.get(key)
            roles = (*was.roles, role) if was and role not in was.roles else (role,)
            kept = was.instances if was else one.selection.instances
            found[key] = Held(roles, kept, one.choice.until, was.why if was else one.choice.why)
    return list(found.values())
