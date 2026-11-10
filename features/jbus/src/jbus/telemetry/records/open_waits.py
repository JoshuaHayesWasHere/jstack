"""The home's `merge-waits.json` (`jmerge.waits`), the spell of each ready pull request still open.
It is `whole`: a spell leaves the file when its pull request merges, is pushed, goes red or
closes, and its row leaves the store with it, so the table holds only what waits now."""

from __future__ import annotations

import json
from datetime import tzinfo

from jbus.telemetry.readers import keyed
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _dict, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    """A spell: an open pull request's wait since it was ready at its head, the code of its open
    segment since `seen`, and the seconds each code held its closed ones."""
    number = one.get("number")
    held = {
        code: seconds
        for code, seconds in _dict(one.get("blockers")).items()
        if isinstance(seconds, int | float) and not isinstance(seconds, bool)
    }
    return {
        "number": int(number) if isinstance(number, str) and number.isdigit() else None,
        "head": _text(one.get("head")),
        "ready": utc(one.get("ready"), zone),
        "ready_by": _text(one.get("ready_by")),
        "code": _text(one.get("code")) or None,
        "seen": utc(one.get("seen"), zone),
        "blockers": json.dumps(held, sort_keys=True),
    }


SOURCE = Source(
    "open_waits",
    "merge-waits.json",
    "snapshot",
    _columns("number", "head", "ready", "ready_by", "code", "seen", "blockers"),
    row,
    at="ready",
    where="home",
    records=keyed("number"),
    natural="number",
    whole=True,
)
