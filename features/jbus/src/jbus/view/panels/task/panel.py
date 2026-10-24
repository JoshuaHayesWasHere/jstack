"""The tasks: the open work of the queue, each in its one state, and the rows that ended while
their status says another thing. Each state is the one that the last pass judged and wrote to
`work.json`: the panel draws it and works none out."""

from __future__ import annotations

from typing import Any

from jbus.view.state import (
    EVENTS_FILE,
    MERGE_LOG,
    MOVES_FILE,
    PASS_FILE,
    QUEUE_FILE,
    WAITING_FILE,
    WORK_FILE,
    Read,
)

FIRST = True
_EVENT = {"at": None, "kind": None, "loud": None, "slug": None, "line": None}
_TASK = {
    "slug": None,
    "pr": None,
    "row_pr": None,
    "status": None,
    "step": None,
    "who": None,
    "state": {"kind": None, "name": None, "say": None, "waits": None, "row": None},
    "rank": None,
    "reason": None,
    "unconfirmed": {"since": None, "source": None, "line": None},
    "blockers": [None],
    "blocked": {"by": None, "what": None, "state": None},
    "blocks": None,
    "behind": [None],
    "since": None,
    "visits": None,
    "priority": None,
    "approved": None,
    "approved_at": None,
    "by_rule": {"rule": None, "follows": None},
    "checks": None,
    "updated": None,
    "thread": None,
    "gone": None,
    "depends": [{"slug": None, "state": None}],
    "history": [{"at": None, "word": None, "step": None, "reason": None}],
    "events": [_EVENT],
    "seen": {
        "threads": None,
        "thread_status": None,
        "thread_updated": None,
        "live": None,
        "wrote": None,
        "run_started": None,
        "queued": None,
        "check": {"name": None, "state": None, "started": None, "completed": None},
    },
    "wave": None,
    "waits_on": None,
    "home": None,
    "retired": None,
}
SHAPE = {"tasks": [_TASK], "ended": [_TASK]}
SOURCES = (PASS_FILE, WORK_FILE, QUEUE_FILE, WAITING_FILE, MOVES_FILE, EVENTS_FILE, MERGE_LOG)


def build(read: Read) -> dict[str, Any]:
    return {"tasks": read.tasks, "ended": read.ended}
