"""What jbus last knew of the default branch's check, read out of `mainmoved`'s `main.json`.

That file is the one record of main's red tip: `broken` is the tip whose check failed, kept
until a green one follows, and `check` is what the tip at `main` says. `mainmoved.tell` is
its only writer, each pass, whether or not a pull request merged lately, and it keeps
`green` there too, the last tip whose check passed. So `red` here is `broken` while the tip
is not green, and `green` is the tip where its check passed, or the one kept before: a tip
whose check has not ended, or was cancelled, changes neither.

Two readers go by it: a launch names `green` on the brief's `Green main:` line (`dispatch`),
and `jmerge` merges no pull request but the fix's while `red` is set (`jmerge.rows`). The fix
is the brief `main-red-<sha12>` that `watch` files ahead of every row, so a slug that starts
with `FIX` is a fix. A file that is missing or cannot be read says nothing is known, and
`jmerge` then merges as it did. A pass of `tell` that still owes a message keeps the
record's commit to look at again and adds `fixed`, the green tip, so a main that turns green
while T3 Code cannot be reached is green here at once. A record from before `broken` was
kept names a failed tip by its `check` alone, and that tip is red too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jbus import read_json

NAME = "main.json"
FIX = "main-red-"
SHA = 12
GREEN = "green"
FIXED = "fixed"


@dataclass(frozen=True)
class Main:
    green: str = ""
    red: str = ""


def of(record: Any) -> Main:
    """What a `main.json` record says of main: nothing known where it is no record."""
    if not isinstance(record, dict):
        return Main()
    keys = ("main", "check", "broken", GREEN, FIXED)
    tip, check, broken, kept, fixed = (record.get(key) or "" for key in keys)
    if not all(isinstance(value, str) for value in (tip, check, broken, kept, fixed)):
        return Main()
    if fixed:
        return Main(green=fixed)
    if check == GREEN:
        return Main(green=tip)
    return Main(green=kept, red=broken or (tip if check == "failed" else ""))


def read(state: Path) -> Main:
    """The word kept in the project's `state`, or nothing known."""
    return of(read_json(state / NAME, {}))


def fix_of(slug: str) -> bool:
    """Whether the slug is the brief of a fix for a red main."""
    return slug.startswith(FIX)
