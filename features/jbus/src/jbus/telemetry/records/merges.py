"""The home's `merge.log`, a log of text lines, not JSON: a row's key is of the line as text."""

from __future__ import annotations

import re
from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, utc

_MERGE_LINE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\S+)(?: #?(\d+))?(?: (\S+))?")
_LABEL = re.compile(r"\[([\w-]+)\]\s*$")


def row(line: str, zone: tzinfo | None) -> Row:
    """A line of `merge.log`, `<YYYY-MM-DD HH:MM> <verb> <number> <url or slug> ...`, in the
    user's zone: its verb, its number, a merge's slug and a wait's `[label]`."""
    found = _MERGE_LINE.match(line)
    label = _LABEL.search(line)
    return {
        "at": utc(found[1], zone) if found else None,
        "verb": found[2] if found else None,
        "number": int(found[3]) if found and found[3] else None,
        "slug": found[4] if found and found[2] == "merged" else None,
        "label": label[1] if label else None,
        "line_len": len(line),
    }


SOURCE = Source(
    "merges",
    "merge.log",
    "log",
    _columns("at", "verb", "number", "slug", "label", "line_len"),
    row,
    where="home",
    text=True,
)
