"""`spend-rows.jsonl` (`jbus.spent`), each read of a day's spend on a row, by its role."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import SPENT, Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "spent_on": _text(one.get("day")),
        "role": _text(one.get("role")),
        "slug": _text(one.get("slug")) or None,
        **{name: _number(one.get(name)) for name in SPENT},
    }


SOURCE = Source(
    "spend_rows",
    "spend-rows.jsonl",
    "log",
    _columns("at", "spent_on", "role", "slug", *SPENT),
    row,
)
