"""The tasks: the open work of the queue, each in its one state, and the rows that ended while
their status says another thing. Each state is the one that the last pass judged and wrote to
`work.json`: the panel draws it and works none out. A task whose row has a fault an agent owns
says who fixes it and when jbus told them (`fixing`, from `state.fixing`).

A task's `now` is the newest of two words with their times: the last line jmerge logged of its
pull request in `merge.log`, and, for a task on the check step, the checks word of its row as
the last pass saw it. The drawer
leads with it, so no older reading stands as the current one."""

from __future__ import annotations

from datetime import datetime
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
    fixing,
    when,
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
    "history": [{"at": None, "word": None, "step": None, "code": None, "reason": None}],
    "events": [_EVENT],
    "seen": {
        "threads": None,
        "thread_status": None,
        "thread_updated": None,
        "live": None,
        "wrote": None,
        "run_started": None,
        "queued": None,
        "reviewer": None,
        "check": {"name": None, "state": None, "started": None, "completed": None},
    },
    "waits_on": None,
    "home": None,
    "retired": None,
    "fixing": {"owner": None, "told": None},
    "now": {"at": None, "by": None, "say": None},
}
SHAPE = {"tasks": [_TASK], "ended": [_TASK]}
SOURCES = (PASS_FILE, WORK_FILE, QUEUE_FILE, WAITING_FILE, MOVES_FILE, EVENTS_FILE, MERGE_LOG)


def now(task: dict[str, Any], passed: str | None) -> dict[str, Any] | None:
    """The newest of jmerge's last line of the task and the pass's checks word, or None where
    neither has a time. jmerge's line wins a tie, since the pass read it."""
    said = []
    if task["history"] and task["history"][-1]["at"]:
        last = task["history"][-1]
        said.append({"at": last["at"], "by": "jmerge", "say": last["reason"] or last["word"]})
    if task["step"] == "check" and task["checks"] and passed:
        said.append({"at": passed, "by": "jbus", "say": f"checks {task['checks']}"})
    return max(said, key=lambda one: datetime.fromisoformat(one["at"]), default=None)


def build(read: Read) -> dict[str, Any]:
    owned, passed = read.once(fixing), when(read.mine.get("seen"))
    return {
        key: [
            task | {"fixing": owned.get(task["slug"]), "now": now(task, passed)} for task in found
        ]
        for key, found in (("tasks", read.tasks), ("ended", read.ended))
    }
