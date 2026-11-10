"""`stalls.jsonl`, each spell a row's thread was quiet or hung (`jbus.stall.spells`), after the
line of when the record began."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    times = {name: utc(one.get(name), zone) for name in ("at", "since", "until")}
    texts = {name: _text(one.get(name)) for name in ("thread", "role", "slug", "became")}
    minutes = one.get("minutes")
    return {**times, **texts, "minutes": minutes if isinstance(minutes, int | float) else None}


SOURCE = Source(
    "stalls",
    "stalls.jsonl",
    "log",
    _columns("at", "thread", "role", "slug", "since", "until", "minutes", "became"),
    row,
)
