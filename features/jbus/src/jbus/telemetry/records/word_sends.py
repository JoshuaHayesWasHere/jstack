"""`word-sends.json` (`jbus.word`), a snapshot of each of the user's words jbus carried
to a home, by its id."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.readers import keyed
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "word": _text(one.get("id")),
        "thread": _text(one.get("thread")) or None,
        "sent_at": utc(one.get("sent_at"), zone),
        "waiting": bool(one.get("waits")),
    }


SOURCE = Source(
    "word_sends",
    "word-sends.json",
    "snapshot",
    _columns("word", "thread", "sent_at", "waiting"),
    row,
    at="sent_at",
    records=keyed("id"),
    natural="word",
)
