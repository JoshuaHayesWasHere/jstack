"""`transitions.jsonl`, each change of a row's status."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _length, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "from_status": _text(one.get("from")),
        "to_status": _text(one.get("to")),
        "by": _text(one.get("by")),
        "why_len": _length(one.get("why")),
        "legal": 0 if one.get("legal") is False else 1,
    }


SOURCE = Source(
    "transitions",
    "transitions.jsonl",
    "log",
    _columns("at", "slug", "from_status", "to_status", "by", "why_len", "legal"),
    row,
)
