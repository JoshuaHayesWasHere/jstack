"""`wakes.json`, the one record of what the one list told each home (`jbus.wakes`).

`jbus.wakes` writes it, and `jbus.leftover`, `jbus.stale` and the view (`state._fixing`) read it.
This module imports nothing of jbus, so that each of them can import it.
"""

from __future__ import annotations

from typing import Any

FILE = "wakes.json"
KIND = "wakes"


def told_to(record: dict[str, Any], thread: str) -> dict[str, dict[str, str]]:
    """What the one list told the thread, by item key, from the record `jbus.wakes.tell` keeps
    in `FILE`:
    `{"threads": {<thread>: {<key>: {"at", "wrong"}}}, "tests": {<run id>: <its tests>},
    "open": [<the line of each open item>]}`."""
    return (record.get("threads") or {}).get(thread) or {}


def opened(record: dict[str, Any]) -> list[str] | None:
    """The line of each item the one list held open at its last pass, from the record's `open`,
    or None for a record written before it kept them (`jbus.stale`)."""
    lines = record.get("open")
    return lines if isinstance(lines, list) else None
