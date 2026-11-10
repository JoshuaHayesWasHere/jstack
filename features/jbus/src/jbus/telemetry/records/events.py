"""`events.jsonl`, jbus's log of what it saw and did."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _length, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "event": _text(one.get("event")),
        "slug": _text(one.get("slug")),
        "loud": _text(one.get("loud")),
        "item": _text(one.get("item")),
        "act": _text(one.get("act")),
        "subject": _text(one.get("subject")),
        "line_len": _length(one.get("line")),
        "text_len": _length(one.get("text")),
    }


SOURCE = Source(
    "events",
    "events.jsonl",
    "log",
    _columns("at", "event", "slug", "loud", "item", "act", "subject", "line_len", "text_len"),
    row,
)
