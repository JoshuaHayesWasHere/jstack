"""`spend.jsonl` (`jbus.spent`), each read of a day's spend, by what was spent and its kinds."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import KINDS, SPENT, Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    spent_on = _text(one.get("day"))
    return {
        "at": utc(one.get("at"), zone),
        "spent_on": spent_on,
        **{name: _number(one.get(name)) for name in (*SPENT, *KINDS)},
    }


SOURCE = Source("spend_days", "spend.jsonl", "log", _columns("at", "spent_on", *SPENT, *KINDS), row)
