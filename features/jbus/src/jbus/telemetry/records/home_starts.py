"""`relaunches.json` (`jbus.children`), a snapshot of each home's last launch, read for the start
before it that failed: one row for each failed start, by its thread, with its cause, when it was
launched and when its failure was seen. jbus drops a home's `failed` once the home starts, and a
later failed start writes over it, but the store keeps each row it saw, so a start that sat with
no `home-id` still counts after its home has started (`jbus.telemetry.launch_failures`)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _dict, _number, _text, utc


def failed(text: str) -> Iterable[Row]:
    """The failed start each home's entry names, with the home's name as `home`."""
    held = json.loads(text)
    if not isinstance(held, dict):
        return []
    return [
        {**_dict(entry.get("failed")), "home": home}
        for home, entry in held.items()
        if isinstance(entry, dict) and _dict(entry.get("failed")).get("thread")
    ]


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "home": _text(one.get("home")),
        "thread": _text(one.get("thread")),
        "cause": _text(one.get("cause")),
        "launched": utc(one.get("launched"), zone),
        "at": utc(one.get("at"), zone),
        "times": _number(one.get("times")),
    }


SOURCE = Source(
    "home_starts",
    "relaunches.json",
    "snapshot",
    _columns("home", "thread", "cause", "launched", "at", "times"),
    row,
    records=failed,
    natural="thread",
)
