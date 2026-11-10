"""`outbox.jsonl` (`jbus.outbox`), each message jbus sent to a thread, by its template."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "thread": _text(one.get("thread")),
        "row": _text(one.get("row")),
        "template": _text(one.get("template")),
        "needs": _text(one.get("needs")),
        "send_key": _text(one.get("key")),
        "went": _text(one.get("went")),
        "rule": _text(one.get("rule")),
    }


SOURCE = Source(
    "outbox",
    "outbox.jsonl",
    "log",
    _columns("at", "thread", "row", "template", "needs", "send_key", "went", "rule"),
    row,
)
