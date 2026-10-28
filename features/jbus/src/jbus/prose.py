"""A deferred action a home writes in its plan is an item of the one list that wakes it.

A line of a home's `plan.md` that defers an action on an event no code watches, "brief once foo
lands" or "on resume", is something a home must remember. jbus does not read the line's meaning:
`deferred` matches it against `PATTERNS`, each within one sentence. Each such line is an item of
the one list (`jbus.wakes`), keyed `prose:<file>:<hash of the line>`, with `<file>` the plan's path
under the root home's directory: the root home's for the root plan, a scope's for its own. It asks
for a row with `--depends`, which code does watch, or for the line to go. A line that is gone or
reworded leaves the list.

`prose.json` in a project's state directory is the record, a `Line` for each key. The first pass
that finds no record writes every line already there as `seeded`, an item of nobody, so only a
line written after it wakes a home. `plan-done.md`, `log/` and the briefs are history or
behaviour, and are not read.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from jbriefs import home as homes
from jbus import read_json, verbs, write_json
from jbus.passes import Pass

NAME = "prose.json"
FILE = "plan.md"
PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bonce\b.*\b(merges|merged|lands|landed|is on main)\b",
        r"\b(on|to) resume\b",
        r"\btakes it out once\b",
        r"\bwhen\b.*\b(merges|lands)\b",
        r"\buntil\b.*\b(merges|lands)\b",
        r"\bre-approve\b.*\b(when|once)\b",
        r"\bwhile\b.*\bholds\b",
    )
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Line:
    """A deferred line: its file under the root home's directory, its text, the scope whose home
    it wakes (empty for the root home), and whether the seed pass found it."""

    file: str
    text: str
    scope: str = ""
    seeded: bool = False


def deferred(line: str) -> bool:
    """Whether one sentence of the line defers an action on an event (`PATTERNS`)."""
    sentences = _SENTENCE.split(line)
    return any(pattern.search(one) for one in sentences for pattern in PATTERNS)


def key_of(file: str, text: str) -> str:
    return f"prose:{file}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def found(home: Path) -> dict[str, Line]:
    """Each deferred line of the root home's plan and of each scope's, by its key."""
    dirs = [(home, "")] + [(scope, scope.name) for scope, _, _ in homes.scopes(home)]
    lines = {}
    for directory, scope in dirs:
        path = directory / FILE
        text = path.read_text(errors="replace") if path.is_file() else ""
        file = path.relative_to(home).as_posix()
        for one in text.splitlines():
            if deferred(one):
                lines[key_of(file, one.strip())] = Line(file, one.strip(), scope)
    return lines


def read(state: Path) -> dict[str, Line] | None:
    """The record of each key, or None before the first pass wrote it or when this module did
    not write the file: the next pass then seeds it again."""
    kept = read_json(state / NAME, None)
    if not isinstance(kept, dict):
        return None
    try:
        return {key: Line(**one) for key, one in kept.items()}
    except TypeError:
        return None


def tell(run: Pass) -> None:
    """Rewrite `prose.json`: each deferred line there is now, seeded on the first pass."""
    was = read(run.state)
    first = was is None
    kept = {
        key: replace(one, seeded=first or (key in was and was[key].seeded))
        for key, one in found(run.home).items()
    }
    if kept != was:
        write_json(run.state / NAME, {key: asdict(one) for key, one in sorted(kept.items())})


STEPS = (verbs.Step("after-derive", 15, "prose.tell", lambda half: tell(half.run)),)
