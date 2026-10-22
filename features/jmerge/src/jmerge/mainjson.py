"""`main.json` contains what jbus last knew of the check of the default branch, and this module
is the one place that defines the file's format.

That file is the one record of main's red tip. `broken` is the tip whose check failed, and the
file keeps it until a green tip follows. `check` is what the check of the tip at `main` says.
`jbus.mainmoved.tell` is the file's only writer. It writes the file each pass, whether or not a
pull request merged lately, and builds each record with `record`. It also keeps `green` there,
the last tip whose check passed, and `pending`, the tips whose check has not ended. Each pass
looks at every tip that main went through since the last pass. When a tip's check failed and a
newer tip's check is still pending, the failed tip is `broken`. When the check of a later tip
passes, the file no longer keeps `broken`. So `red` here is `broken` while the tip is not green.
`green` is the tip whose check passed, or the green tip kept before. A tip whose check has not
ended, or was cancelled, changes neither.

Two readers go through `read`. A launch names `green` on the brief's `Green main:` line
(`jbus.dispatch`), and while `red` is set, `jmerge` merges no pull request but the fix's
(`jmerge.rows`). The fix is the brief `main-red-<sha12>` that `jbus.watch` files ahead of
every row, so a slug that starts with `FIX` is a fix. A file that is missing or cannot be read
means nothing is known, and `jmerge` then merges as it did before. When a pass of `tell` has
not yet sent its message, it keeps the record's commit so that the next pass looks at that
commit again. It also adds `fixed`, the green tip, as `owed` does. So a main that turns green
while T3 Code cannot be reached is green here at once. When `rebase.held` keeps back a pass's
message, that pass does the same. Older records, written before the file kept `broken`, name a
failed tip only by its `check`, and that tip is red too.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

NAME = "main.json"
FIX = "main-red-"
SHA = 12
Check = Literal["green", "failed", "pending", "cancelled", "refused"]
SETTLED: tuple[Check, ...] = ("green", "failed")


class Record(TypedDict):
    """What the file contains."""

    main: str
    """The 40-hex tip of origin's default branch."""
    at: str
    """When `main` was first seen there, ISO-8601 with its offset, kept while it is unchanged."""
    check: Check
    """What the check of `main` says."""
    broken: NotRequired[str]
    """The red tip, kept until a green tip follows it."""
    green: NotRequired[str]
    """The last tip whose check passed."""
    pending: NotRequired[list[str]]
    """The tips whose check has not ended, oldest first, looked at again each pass."""
    held: NotRequired[list[str]]
    """The slugs whose main-moved message `rebase.held` kept back."""
    fixed: NotRequired[str]
    """The green tip that ended `broken`, written on the owed path: it reads as green."""


_TEXTS = ("main", "at", "check", "broken", "green", "fixed")
_LISTS = ("pending", "held")


@dataclass(frozen=True)
class Main:
    green: str = ""
    red: str = ""


def of(record: object) -> Main:
    """What a `main.json` record says of main. When the value is not a record, it says that
    nothing is known."""
    if not isinstance(record, dict):
        return Main()
    keys = ("main", "check", "broken", "green", "fixed")
    tip, check, broken, kept, fixed = (record.get(key) or "" for key in keys)
    if not all(isinstance(value, str) for value in (tip, check, broken, kept, fixed)):
        return Main()
    if fixed:
        return Main(green=fixed)
    if check == "green":
        return Main(green=tip)
    return Main(green=kept, red=broken or (tip if check == "failed" else ""))


def _raw(state: Path) -> object:
    try:
        return json.loads((state / NAME).read_text())
    except (OSError, ValueError):
        return None


def read(state: Path) -> Main:
    """What `main.json` in the project's `state` says of main, or nothing known."""
    return of(_raw(state))


def typed(raw: object) -> Record | None:
    """A record as its writer reads it back, with each key of the right type and no other key.

    `typed` drops each key of the wrong type and keeps the rest, so an unreadable `held`
    does not also lose the red tip. It returns None where the value is not a record at all."""
    if not isinstance(raw, dict):
        return None
    kept = {key: raw[key] for key in _TEXTS if isinstance(raw.get(key), str)}
    for key in _LISTS:
        value = raw.get(key)
        if isinstance(value, list) and all(isinstance(one, str) for one in value):
            kept[key] = value
    return kept  # type: ignore[return-value]


def load(state: Path) -> Record | None:
    """The record kept in the project's `state` (`typed`), or None where there is none."""
    return typed(_raw(state))


def record(
    *,
    main: str,
    at: str,
    check: Check,
    broken: str = "",
    green: str = "",
    held: Sequence[str] = (),
    fixed: str = "",
    pending: Sequence[str] = (),
) -> Record:
    """The record of a pass, with no key for a value it was not given."""
    made: Record = {"main": main, "at": at, "check": check}
    if broken:
        made["broken"] = broken
    if fixed:
        made["fixed"] = fixed
    if pending:
        made["pending"] = list(pending)
    if green:
        made["green"] = green
    if held:
        made["held"] = list(held)
    return made


def owed(was: Record, fixed: str) -> Record:
    """The record that a pass leaves when it has not yet sent its message. It is the last
    record with `fixed` added, so that its readers see main as green at `fixed`."""
    return {**was, "fixed": fixed}


def fix_of(slug: str) -> bool:
    """Whether the slug is the brief of a fix for a red main."""
    return slug.startswith(FIX)
