"""`spend-rows.jsonl` (`jbus.spent`), each read of a day's spend on a row, by its role and by what
woke its runs (`jgauge.spend.day_lines`). A line kept before the trigger was has none: its
`trigger`, `reviewed` and `dollars` are NULL."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import SPENT, Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    reviewed, dollars = one.get("reviewed"), one.get("dollars")
    return {
        "at": utc(one.get("at"), zone),
        "spent_on": _text(one.get("day")),
        "role": _text(one.get("role")),
        "slug": _text(one.get("slug")) or None,
        **{name: _number(one.get(name)) for name in SPENT},
        "trigger": _text(one.get("trigger")),
        "reviewed": int(reviewed) if isinstance(reviewed, bool) else None,
        "dollars": float(dollars)
        if isinstance(dollars, int | float) and not isinstance(dollars, bool)
        else None,
    }


SOURCE = Source(
    "spend_rows",
    "spend-rows.jsonl",
    "log",
    _columns("at", "spent_on", "role", "slug", *SPENT, "trigger")
    + (("reviewed", "INTEGER"), ("dollars", "REAL")),
    row,
)
