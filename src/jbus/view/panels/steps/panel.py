"""The line: its twelve steps from Queued to Merged, the lane of a task whose state the
view cannot work out, and how many rows the queue has in each status."""

from __future__ import annotations

from typing import Any

from jbus import queue
from jbus.view.clean import ANY
from jbus.view.state import QUEUE_FILE, STEPS, UNKNOWN, Read, Spot, Step, text

FIRST = True
_STEP = {"key": None, "name": None, "who": None, "note": None, "group": None}
SHAPE = {
    "steps": [_STEP],
    "unknown": _STEP,
    "queue": {"total": None, "by_status": {ANY: None}},
}
SOURCES = (QUEUE_FILE,)
NOT_KEPT = (Spot("the step a task of unknown state is on is not guessed", 520),)


def blind(read: Read) -> list[Spot]:
    """How many open tasks have no time on their step."""
    untimed = sum(1 for task in read.tasks if task["since"] is None)
    return [Spot(f"{untimed} open tasks have no time on their step", 100)] if untimed else []


def _said(step: Step) -> dict[str, str]:
    return {
        "key": step.key,
        "name": step.name,
        "who": step.who,
        "note": step.note,
        "group": step.group,
    }


def build(read: Read) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for row in read.rows:
        word = text(row.get("status")) or "queued"
        word = word if word in queue.STATUSES else "other"
        by_status[word] = by_status.get(word, 0) + 1
    return {
        "steps": [_said(step) for step in STEPS],
        "unknown": _said(UNKNOWN),
        "queue": {"total": len(read.rows), "by_status": by_status},
    }
