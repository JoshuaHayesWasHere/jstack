"""The home's `merge-waits.jsonl` (`jmerge.waits`), each merged pull request's wait."""

from __future__ import annotations

import json
from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _dict, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    """A line of `merge-waits.jsonl`: a merged pull request's wait from ready to the second its
    merge began, the seconds each code held it, and the code that held it longest."""
    held = {
        code: seconds
        for code, seconds in _dict(one.get("blockers")).items()
        if isinstance(seconds, int | float) and not isinstance(seconds, bool)
    }
    return {
        "at": utc(one.get("began"), zone),
        "number": _number(one.get("number")),
        "head": _text(one.get("head")),
        "ready": utc(one.get("ready"), zone),
        "ready_by": _text(one.get("ready_by")),
        "seconds": one["seconds"] if isinstance(one.get("seconds"), int | float) else None,
        "blocker": max(sorted(held), key=held.__getitem__) if held else None,
        "blockers": json.dumps(held, sort_keys=True),
    }


SOURCE = Source(
    "merge_waits",
    "merge-waits.jsonl",
    "log",
    _columns("at", "number", "head", "ready", "ready_by", "seconds", "blocker", "blockers"),
    row,
    where="home",
)
