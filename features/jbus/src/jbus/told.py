"""`wakes.json`, the one record of what the one list told each home (`jbus.wakes`).

`jbus.wakes` writes it, and `jbus.leftover` and the view (`state._fixing`) read it. This module
imports nothing of jbus, so that each of them can import it.
"""

from __future__ import annotations

from typing import Any

FILE = "wakes.json"
KIND = "wakes"


def told_to(record: dict[str, Any], thread: str) -> dict[str, dict[str, str]]:
    """What the one list told the thread, by item key, from the record `jbus.wakes.tell` keeps
    in `FILE`:
    `{"threads": {<thread>: {<key>: {"at", "wrong"}}}, "tests": {<run id>: <its tests>}}`."""
    return (record.get("threads") or {}).get(thread) or {}
