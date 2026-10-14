"""The bus: what the outbox and the wakes count, what was sent today by kind and loudness,
and the last events of the log. The outbox itself is never opened."""

from __future__ import annotations

from typing import Any

from jbus import read_json
from jbus.view.clean import ANY
from jbus.view.state import EVENTS_FILE, Read, Spot, kept, text, when
from jbus.wake import LOUDNESS

FIRST = True
SHOWN = 40
_EVENT = {"at": None, "kind": None, "loud": None, "slug": None, "line": None}
SHAPE = {
    "bus": {
        "outbox": None,
        "failed_wakes": None,
        "last_error": None,
        "posted": None,
        "sent": None,
        "sent_kinds": {ANY: None},
        "stalls": None,
        "loudness": {ANY: None},
        "today": {ANY: None},
        "events": [_EVENT],
    }
}
NOT_KEPT = (Spot("the time each step of a pass took is not kept", 510),)


def sent(read: Read) -> list[Any] | None:
    """The keys `sent.json` keeps, or None where it holds no list."""
    kept = read_json(read.state / "sent.json", None)
    return kept if isinstance(kept, list) else None


SOURCES = (
    EVENTS_FILE,
    kept("stall.json", lambda read: read.table("stall.json"), 100),
    kept("wake.json", lambda read: read.table("wake.json"), 110),
    kept("sent.json", lambda read: read.once(sent), 120),
)


def build(read: Read) -> dict[str, Any]:
    status = read.panel("pulse")["jbus"]["status"]
    wake, keys = read.table("wake.json") or {}, read.once(sent) or []
    today: dict[str, int] = {}
    for one in read.events:
        if one["at"] >= read.day:
            today[one["kind"]] = today.get(one["kind"], 0) + 1
    by_kind: dict[str, int] = {}
    for key in keys:
        kind = text(key).partition("|")[0]
        kind = kind if kind in LOUDNESS else "other"
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "bus": {
            "outbox": status["outbox"],
            "failed_wakes": status["failed_wakes"],
            "last_error": text(wake.get("last_error")) or status["last_error"],
            "posted": when(wake.get("posted")),
            "sent": len(keys),
            "sent_kinds": by_kind,
            "stalls": len(read.table("stall.json") or {}),
            "loudness": dict(LOUDNESS),
            "today": today,
            "events": read.events[-SHOWN:],
        }
    }
