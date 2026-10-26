"""What merged today: each row that moved to merged in the queue since the start of the user's
day, and each row that `merge.log` records as merged while the row says another state
(`Read.merged_since`)."""

from __future__ import annotations

from typing import Any

from jbus.view.state import MERGE_LOG, MOVES_FILE, QUEUE_FILE, Read

FIRST = True
SHAPE = {"merged": [{"slug": None, "pr": None, "at": None, "approved": None}]}
SOURCES = (QUEUE_FILE, MOVES_FILE, MERGE_LOG)


def build(read: Read) -> dict[str, Any]:
    return {"merged": read.merged_since(read.day)}
