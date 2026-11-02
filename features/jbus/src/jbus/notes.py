"""A dated line that lands in a home's `notes.md` is an item of the one list that wakes it.

The user's word (2026-10-28): homes add no entries to `notes.md`. A standing rule written there is
read by no code and goes stale, so it belongs in the plan, a brief or code. A line of the file that
starts with a date, as a bulleted `- 2026-11-02: ...` or a heading, is such an entry; a line with
no date is not. Each home's file, the root home's and each scope's, is one item of the one list
(`jbus.wakes`), keyed `notes:<file>` with `<file>` its path under the root home's directory. Its
words name the newest dated line the last pass found new, so a home is told again only when a new
line lands, and a line moved out of the file wakes nobody. The first pass that sees a file finds
every dated line in it new, and tells its home of them through the newest. jbus reads the file
and never writes or deletes it: the home moves each entry out.

`notes.json` in a project's state directory is the record, a `Note` for each file that holds a
dated line.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from jbriefs import home as homes
from jbus import read_json, verbs, write_json
from jbus.passes import Pass

NAME = "notes.json"
FILE = "notes.md"
DATED = re.compile(r"^(?:[-*+]|#{1,6})?\s*\d{4}-\d{2}-\d{2}\b")


@dataclass(frozen=True)
class Note:
    """A home's file: its path under the root home's directory, the scope whose home it wakes
    (empty for the root home), the hashes of its dated lines as the last pass found them, the
    newest dated line that a pass found new, and how many dated lines the file held then."""

    file: str
    scope: str
    seen: tuple[str, ...]
    last: str
    dated: int


def dated(text: str) -> list[str]:
    """The lines of the text that start with a date, stripped, in the file's order."""
    return [one.strip() for one in text.splitlines() if DATED.match(one.strip())]


def _hash(line: str) -> str:
    return hashlib.sha256(line.encode()).hexdigest()[:12]


def key_of(file: str) -> str:
    return f"notes:{file}"


def read(state: Path) -> dict[str, Note]:
    """The record of each file, by its key; empty before the first pass wrote it."""
    kept = read_json(state / NAME, {})
    if not isinstance(kept, dict):
        return {}
    try:
        return {key: Note(**{**one, "seen": tuple(one["seen"])}) for key, one in kept.items()}
    except (TypeError, KeyError):
        return {}


def tell(run: Pass) -> None:
    """Rewrite `notes.json`: each home's file that holds a dated line, with the newest line that
    is new since the last pass, or the one it had when none is."""
    was = read(run.state)
    dirs = [(run.home, "")] + [(scope, scope.name) for scope, _, _ in homes.scopes(run.home)]
    kept = {}
    for directory, scope in dirs:
        path = directory / FILE
        lines = dated(path.read_text(errors="replace")) if path.is_file() else []
        if not lines:
            continue
        file = path.relative_to(run.home).as_posix()
        key, seen = key_of(file), tuple(sorted({_hash(one) for one in lines}))
        before = was.get(key)
        new = [one for one in lines if not before or _hash(one) not in before.seen]
        if new:
            kept[key] = Note(file, scope, seen, new[-1], len(lines))
        elif before:
            kept[key] = Note(file, scope, seen, before.last, before.dated)
    if kept != was:
        write_json(run.state / NAME, {key: asdict(one) for key, one in sorted(kept.items())})


STEPS = (verbs.Step("after-derive", 16, "notes.tell", lambda half: tell(half.run)),)
