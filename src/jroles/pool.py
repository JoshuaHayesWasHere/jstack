"""Which instance of a role's pool a launch or a move goes to.

A role line names its pool in order (`crew: claudeAgent claude-opus-5-5
claudeAgent,claudeAgent_claude_prime`). `choose` takes the first instance of it with headroom in
the ledger (`jroles.ledger`): an instance is out only while one of its windows is full and has
not reset. So every launch goes to the first account until it is capped, and a thread stays on
the account it started on; nothing goes round the pool launch by launch. With every instance
capped there is no instance, and the choice says when the first of them resets.

The pool grows by a line of the provider inventory (`~/.config/jstack/providers.json`, T3
Code's `providerInstances`) and one more id on the role line: an id the inventory does not
declare under the line's provider refuses the line, so a Claude pool never names a Codex or a
Cursor instance. Where there is no inventory the line is taken as it is written.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jroles import Refused, Selection, ledger, read_map

WAIT = 75


@dataclass(frozen=True)
class Choice:
    """Where a launch or a move goes, and why it is not the pool's first instance. `instance`
    is None while every instance is capped, and `until` is then the first reset."""

    instance: str | None
    why: str
    until: datetime | None = None


def choose(pool: tuple[str, ...], kept: ledger.Ledger, now: datetime) -> Choice:
    """The first instance of `pool` with headroom in `kept`."""
    capped = []
    for instance in pool:
        until = ledger.capped_until(kept, instance, now)
        if until is None:
            why = "; ".join(f"{name} is capped until {at.isoformat()}" for name, at in capped)
            return Choice(instance, why)
        capped.append((instance, until))
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
    """Each instance the inventory declares, with its driver. Refused when it is not in T3's
    `providerInstances` shape."""
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
    provider. The provider's built-in instance needs no line. None is no inventory."""
    if drivers is None:
        return
    for instance in selection.pool:
        if instance != selection.provider and drivers.get(instance) != selection.provider:
            raise Refused(
                f"refused {role}: {instance} is no {selection.provider} instance of providers.json"
            )


@dataclass(frozen=True)
class Route:
    """A role's selection and the instance of its pool the ledger leaves it."""

    selection: Selection
    choice: Choice

    def as_json(self) -> dict[str, object]:
        return self.selection.as_json(self.choice.instance)


def selection(role: str) -> Selection | None:
    """The role's line of the map, its pool checked against the inventory, or None where the
    role inherits. Refused for a map or an inventory it cannot use."""
    where = config_dir()
    try:
        text = (where / "roles").read_text()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "it is not UTF-8"
        raise Refused(f"cannot read {where / 'roles'}: {reason}") from error
    chosen = read_map(text, role)
    if chosen is None:
        return None
    try:
        drivers = declared((where / "providers.json").read_text())
    except FileNotFoundError:
        drivers = None
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(f"refused {role}: providers.json cannot be read ({error})") from error
    check(role, chosen, drivers)
    return chosen


def route(role: str, now: datetime) -> Route | None:
    """Where a launch of `role` goes now, or None where it inherits."""
    chosen = selection(role)
    if chosen is None:
        return None
    pool = chosen.instances
    return Route(chosen, choose(pool, ledger.read(pool), now))
