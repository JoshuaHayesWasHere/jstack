"""The queue as a flow: every queued row and every row that is out, with a column for each wave.
It draws the tasks that the task panel gives, and has no data of its own."""

from __future__ import annotations

from typing import Any

from jbus.view.state import QUEUE_FILE, Read

FIRST = True
SHAPE: dict[str, Any] = {}
SOURCES = (QUEUE_FILE,)


def build(read: Read) -> dict[str, Any]:
    return {}
