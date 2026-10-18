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
`jmerge` then merges as it did. `tell` writes the record only once no message it owes is
left to send, so a main that turns green while T3 Code cannot be reached stays red here
until the next pass that gets through.
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


@dataclass(frozen=True)
class Main:
    green: str = ""
    red: str = ""


def of(record: Any) -> Main:
    """What a `main.json` record says of main: nothing known where it is no record."""
    if not isinstance(record, dict):
        return Main()
    tip, check, broken, kept = (record.get(key, "") for key in ("main", "check", "broken", GREEN))
    if not all(isinstance(value, str | None) for value in (tip, check, broken, kept)):
        return Main()
    if check == GREEN:
        return Main(green=tip or "")
    return Main(green=kept or "", red=broken or "")


def read(state: Path) -> Main:
    """The word kept in the project's `state`, or nothing known."""
    return of(read_json(state / NAME, {}))


def fix_of(slug: str) -> bool:
    """Whether the slug is the brief of a fix for a red main."""
    return slug.startswith(FIX)
