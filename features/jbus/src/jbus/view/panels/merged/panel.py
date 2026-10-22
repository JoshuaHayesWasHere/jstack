"""What merged today: each row the queue moved to merged since the start of the user's day,
and each row `merge.log` has as merged while its row says another thing."""

from __future__ import annotations

from typing import Any

from jbus import queue
from jbus.view.state import MERGE_LOG, MOVES_FILE, QUEUE_FILE, Read, text, when

FIRST = True
SHAPE = {"merged": [{"slug": None, "pr": None, "at": None, "approved": None}]}
SOURCES = (QUEUE_FILE, MOVES_FILE, MERGE_LOG)


def build(read: Read) -> dict[str, Any]:
    pull = {row["slug"]: row for row in read.rows}
    merged = []
    for move in read.moves or []:
        slug, at = text(move.get("slug"), 80), when(move.get("at"))
        if move.get("to") == "merged" and at and at >= read.day:
            was = pull.get(slug, {})
            approved = when(queue.ran_at(was), read.user)
            merged.append(
                {"slug": slug, "pr": text(was.get("pr"), 20), "at": at, "approved": approved}
            )
    for one in read.ended:
        at = one["since"] if one["state"]["kind"] == "merged" else None
        if at and at >= read.day and one["slug"] not in {m["slug"] for m in merged}:
            approved = one["approved_at"]
            merged.append({"slug": one["slug"], "pr": one["pr"], "at": at, "approved": approved})
    merged.sort(key=lambda one: one["at"])
    return {"merged": merged}
