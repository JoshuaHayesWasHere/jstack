"""`review-launches.jsonl` (`jbus.reviewlaunch`), the head each reviewer thread was launched at,
one row a thread: its slug, its kind (`first` or
`scoped`) and its `number`, the seat `#<n>` of a first reviewer, 1 for a scoped one."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "thread": _text(one.get("thread")),
        "head": _text(one.get("head")),
        "kind": _text(one.get("kind")),
        "number": _number(one.get("n")),
    }


SOURCE = Source(
    "review_heads",
    "review-launches.jsonl",
    "snapshot",
    _columns("at", "slug", "thread", "head", "kind", "number"),
    row,
    natural="thread",
)
