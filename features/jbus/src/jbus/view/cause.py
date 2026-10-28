"""The cause of a task: why it is where it is, in plain words, since when, and whether it moves.

`cause` reads one task of `/state.json`, as `panels/task/panel.py` gives its shape, and works out
nothing that the task does not already hold. The pass judged the state (`jbus.work`) and the view
worded it for the pass's readers (`state.say`). This module words it for a person who looks at a
board and asks what blocks a row: the check a row waits on, how long a thread has been silent, the
row it is behind.

Each value of `work.VALUES` has at most one wording here, in `WORDS`. A value with none gives the
task's `state.say`, so no task is left with an empty line.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jbus.view import checked
from jbus.view.state import NO_REVIEWER

STACKED = checked.STACKED_TEXT[0]
_AFTER = re.compile(r"merges after ([a-z0-9][a-z0-9._-]*)")


@dataclass(frozen=True)
class Cause:
    """Why a task is where it is. `since` is an ISO time, or None where the task has none."""

    text: str
    since: str | None
    moving: bool


def age(since: str | None, now: datetime) -> str:
    """How long ago `since` was, as the board writes it: `14m`, `2h05`, `3d04`."""
    if since is None:
        return ""
    minutes = max(int((now - datetime.fromisoformat(since)).total_seconds() // 60), 0)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d{hours:02d}"
    return f"{hours}h{minutes:02d}" if hours else f"{minutes}m"


def _ago(since: str | None, now: datetime) -> str:
    return f"{age(since, now)} ago" if since else ""


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _seen(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("seen") or {}


def _say(task: dict[str, Any]) -> str:
    state = task.get("state") or {}
    return state.get("say") or state.get("name") or state.get("kind") or "no state was given"


def _heard(task: dict[str, Any]) -> str | None:
    """When the task's thread last wrote, or else since when the task is in its step."""
    seen = _seen(task)
    return seen.get("wrote") or seen.get("thread_updated") or task.get("since")


def _check(task: dict[str, Any], now: datetime) -> Cause:
    reason = task.get("reason") or ""
    if STACKED in reason:
        after = _AFTER.search(reason)
        parent = after[1] if after else (task.get("blockers") or [task.get("waits_on") or ""])[0]
        return Cause(_join("merges after", parent or "its parent row"), task.get("since"), False)
    check = _seen(task).get("check") or {}
    state = check.get("state")
    if checked.outcome(task) == checked.FAILING and state != "failed":
        return Cause("a check failed", task.get("since"), False)
    if state == "pending":
        started = check.get("started")
        name = check.get("name") or "its check"
        if not started:
            return Cause(f"{name} queued, waits for a runner", task.get("since"), False)
        return Cause(_join(name, "running", age(started, now)), started, True)
    if state in ("passed", "failed"):
        done = check.get("completed")
        text = _join("check", state, _ago(done, now))
        if state == "passed":
            text += ", jmerge has not moved it on"
        return Cause(text, done, False)
    return Cause(_say(task), task.get("since"), False)


def _working(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("thread working", task.get("since"), True)


def _launching(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("thread starting", task.get("since"), True)


def _quiet(task: dict[str, Any], now: datetime) -> Cause:
    heard = _heard(task)
    return Cause(_join("thread silent", age(heard, now)), heard, False)


def _hung(task: dict[str, Any], now: datetime) -> Cause:
    heard = _heard(task)
    return Cause(_join("turn silent", age(heard, now)) + ", may be hung", heard, False)


def _lost(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("thread gone with nothing written, needs your word", task.get("since"), False)


def _behind(task: dict[str, Any], now: datetime) -> Cause:
    blocked = task.get("blocked") or {}
    first = blocked.get("what") or (task.get("blockers") or [task.get("waits_on") or ""])[0]
    return Cause(_join("behind", first or "a row in front of it"), task.get("since"), False)


def _unapproved(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("waits for your approval", task.get("since"), False)


def _leftover(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("ended with something left: close it or say why", task.get("since"), False)


def _asking(task: dict[str, Any], now: datetime) -> Cause:
    return Cause(f"asks you: {_say(task)}", task.get("since"), False)


def _review(task: dict[str, Any], now: datetime) -> Cause:
    """A review runs only where a reviewer's thread of the task is out (`seen.reviewer`). The
    view's say tells no running reviewer: it gives NO_REVIEWER only after `REVIEW_MINUTES`."""
    since, reviewer = task.get("since"), _seen(task).get("reviewer")
    if reviewer:
        return Cause(_join("review running", age(since, now)), since, True)
    if reviewer is False or _say(task) == NO_REVIEWER:
        waited = f"in {age(since, now)}" if since else ""
        return Cause(_join(NO_REVIEWER, waited), since, False)
    on = _join("on review", age(since, now))
    return Cause(f"{on}, with no list of threads to show a reviewer", since, False)


def _second(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("second review not written yet", task.get("since"), False)


def _findings(task: dict[str, Any], now: datetime) -> Cause:
    return Cause("findings not handled yet by its crewmate", task.get("since"), False)


def _rebase(task: dict[str, Any], now: datetime) -> Cause:
    return Cause(f"needs a rebase by its crewmate: {_say(task)}", task.get("since"), False)


def _proof(task: dict[str, Any], now: datetime) -> Cause:
    return Cause(f"needs a proof from its reviewer: {_say(task)}", task.get("since"), False)


def _hold(task: dict[str, Any], now: datetime) -> Cause:
    return Cause(f"held for your word: {_say(task)}", task.get("since"), False)


WORDS: dict[str, Callable[[dict[str, Any], datetime], Cause]] = {
    "check": _check,
    "working": _working,
    "launching": _launching,
    "quiet": _quiet,
    "hung": _hung,
    "lost": _lost,
    "behind": _behind,
    "unapproved": _unapproved,
    "leftover": _leftover,
    "asking": _asking,
    "review": _review,
    "second": _second,
    "findings": _findings,
    "rebase": _rebase,
    "proof": _proof,
    "hold": _hold,
}


def cause(task: dict[str, Any], now: datetime) -> Cause:
    """Why `task` is where it is at `now`. Its value is its `state.kind`, one of `work.VALUES`."""
    words = WORDS.get((task.get("state") or {}).get("kind") or "")
    return words(task, now) if words else Cause(_say(task), task.get("since"), False)
