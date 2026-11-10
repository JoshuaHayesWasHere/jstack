"""`items.jsonl`, jbus's row records: each verb on an item of the queue."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _length, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "id": _text(one.get("id")),
        "at": utc(one.get("at"), zone),
        "item": _text(one.get("item")),
        "verb": _text(one.get("verb")),
        "slug": _text(one.get("slug")) or None,
        "by": _text(one.get("by")),
        "by_user": _text(one.get("by_user")),
        "place": _text(one.get("where")),
        "title_len": _length(one.get("title")),
        "line_len": _length(one.get("line")),
    }


SOURCE = Source(
    "items",
    "items.jsonl",
    "log",
    _columns("id", "at", "item", "verb", "slug", "by", "by_user", "place", "title_len", "line_len"),
    row,
)
