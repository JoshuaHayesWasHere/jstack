"""Which instance of a role's pool a launch or a move goes to.

A role line names its pool in order (`crew: claudeAgent claude-opus-5-5
claudeAgent,claudeAgent_claude_prime`). `choose` takes the first instance of the pool with
headroom in the ledger (`jroles.ledger`). An instance is out only while one of its windows is
full and has not reset. A new launch counts a window full at the user's `headroom`
(`jsettings`, 90 by default). A move off a running thread (`jbus.failover`) counts it full only
at a real cap, 100. So every launch goes to the first account until that account nears its
cap, and a thread stays on the account it started on until that account is capped. No launch
rotates through the pool. When every instance is full, the choice has no instance, and it says
when the first of them resets.

To grow the pool, add a line to the provider inventory (`~/.config/jstack/providers.json`, T3
Code's `providerInstances`) and one more id to the role line. `jroles` refuses a line with an id
that the inventory does not declare under the line's provider, so a Claude pool never names a
Codex or a Cursor instance. When there is no inventory, `jroles` takes the line as it is written.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jsettings
from jroles import Refused, Selection, ledger, read_map

WAIT = 75


@dataclass(frozen=True)
class Choice:
    """Where a launch or a move goes, and why it is not the pool's first instance. `instance`
    is None while every instance is capped or passed over. `until` is then the first reset, or
    None when no instance is capped. `passed` holds each instance that `skip` passed over."""

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
    is used to `full` or more. The function passes over each instance that `skip` names, for
    the reason `skip` gives (`jbus` skips an instance that is not mirrored). When `skip` passes
    over every instance, there is no instance and no reset to wait for."""
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


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "jstack"


def declared(text: str) -> dict[str, str]:
    """Each instance that the inventory declares, with its driver. The function refuses an
    inventory that is not in T3's `providerInstances` shape."""
    try:
        found = json.loads(text)
    except ValueError as error:
        raise Refused(f"refused: providers.json is not JSON ({error})") from error
    if not isinstance(found, dict) or not all(
        isinstance(entry, dict) and isinstance(entry.get("driver"), str) for entry in found.values()
    ):
        raise Refused("refused: providers.json is not an object of instances with a driver")
    return {str(name): entry["driver"] for name, entry in found.items()}


def check(role: str, selection: Selection, drivers: dict[str, str] | None) -> None:
    """Refuse a pool that names an instance the inventory does not declare under the line's
    provider. The provider's built-in instance needs no line in the inventory. An inventory of
    None means there is no inventory."""
    if drivers is None:
        return
    for instance in selection.pool:
        if instance != selection.provider and drivers.get(instance) != selection.provider:
            raise Refused(
                f"refused {role}: {instance} is no {selection.provider} instance of providers.json"
            )


@dataclass(frozen=True)
class Route:
    """A role's selection, and the instance of its pool that the ledger leaves it."""

    selection: Selection
    choice: Choice

    def as_json(self) -> dict[str, object]:
        return self.selection.as_json(self.choice.instance)


def selections(role: str) -> tuple[Selection, ...]:
    """The role's lines of the map, in order, with each pool checked against the inventory,
    or none when the role inherits. Only `review` has more than one line. The function refuses
    a map or an inventory that it cannot use."""
    where = config_dir()
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
    try:
        drivers = declared((where / "providers.json").read_text())
    except FileNotFoundError:
        drivers = None
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(f"refused {role}: providers.json cannot be read ({error})") from error
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
