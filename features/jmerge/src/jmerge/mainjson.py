"""`main.json`: what jbus last knew of the default branch's check, and the one place its
shape is written down.

That file is the one record of main's red tip: `broken` is the tip whose check failed, kept
until a green one follows, and `check` is what the tip at `main` says. `jbus.mainmoved.tell`
is its only writer, each pass, whether or not a pull request merged lately, and it builds
each record with `record`. It keeps `green` there too, the last tip whose check passed, and
`pending`, the tips whose check has not ended. It looks at every tip main went through since
its last pass, so a tip that failed under a newer one still pending is `broken`, and one that
passed after `broken` ends it. So `red` here is `broken` while the tip is not green, and
`green` is the tip where its check passed, or the one kept before: a tip whose check has not
ended, or was cancelled, changes neither.

Two readers go by `read`: a launch names `green` on the brief's `Green main:` line
(`jbus.dispatch`), and `jmerge` merges no pull request but the fix's while `red` is set
(`jmerge.rows`). The fix is the brief `main-red-<sha12>` that `jbus.watch` files ahead of
every row, so a slug that starts with `FIX` is a fix. A file that is missing or cannot be
read says nothing is known, and `jmerge` then merges as it did. A pass of `tell` that still
owes a message keeps the record's commit to look at again and adds `fixed`, the green tip
(`owed`), so a main that turns green while T3 Code cannot be reached is green here at once,
and so does a pass whose message `rebase.held` kept back. A record from before `broken` was
kept names a failed tip by its `check` alone, and that tip is red too.
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
    """What the file holds."""

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
    """What a `main.json` record says of main: nothing known where it is no record."""
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
    """The word kept in the project's `state`, or nothing known."""
    return of(_raw(state))


def typed(raw: object) -> Record | None:
    """A record as its writer reads it back: each key of the right type, and none other.

    A key of the wrong type is dropped by itself, so a `held` that cannot be read does not
    take the red tip with it. None where it is no record at all."""
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
    """The record of a pass, with no key for what it was not given."""
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
    """The record a pass that still owes a send leaves: the last one, with main green at
    `fixed` for its readers."""
    return {**was, "fixed": fixed}


def fix_of(slug: str) -> bool:
    """Whether the slug is the brief of a fix for a red main."""
    return slug.startswith(FIX)
