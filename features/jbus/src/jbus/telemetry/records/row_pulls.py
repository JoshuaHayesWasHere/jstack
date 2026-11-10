"""`row-pulls.jsonl` (`jbus.history`), each state a row's pull request was seen in."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "number": _number(one.get("number")),
        "state": _text(one.get("state")),
        "branch": _text(one.get("branch")),
        "head": _text(one.get("head")),
        "merged_at": utc(one.get("merged_at"), zone),
    }


SOURCE = Source(
    "row_pulls",
    "row-pulls.jsonl",
    "log",
    _columns("at", "slug", "number", "state", "branch", "head", "merged_at"),
    row,
)
