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
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jsettings
from jroles import Refused, Selection, inventory, ledger, read_map

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
