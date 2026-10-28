"""What the check of a row in check did: it failed, it runs or waits for a runner, it passed and
the row waits for `jmerge`, or the row is stacked and merges after another.

A row is in check where the last pass put it on the step `check`. `jmerge` puts a stacked pull
request on that step too, one that merges after its parent row (`jmerge.ready`'s `STACKED_ON`,
`STACKED_UNMOVED`, `MERGES_AFTER` and `CARRIES_AFTER`), so `stacked` comes first, whatever its own
checks say: it is the last line `jmerge` logged of the row, by that line's code, or, for a line
logged before the codes, by the code its text gives (`ready.code_of`), one of `STACKED_CODES`. A
row with no line is read by its reason, and a reason that says `STACKED_ON`, as jbus words a
stacked row, is stacked too. Any other outcome comes from the row's `checks`, the one word
`jmerge --checks` reads from the latest run of each check of the pull request
(`jmerge.checks.checks`), which the pass writes beside the row (`watch.checks`). So a red lint
beside a check that still runs is a failing row, as it is to `jmerge`. `OUTCOME` is the one table
of the words: `failed`, which also holds a check that never started beside checks that ran;
`pending` and `none`, where no check has answered yet; and `passed`. A row whose word is `unrun`
(every check skipped at its head), `draft` or none at all is in check and has none of the
outcomes: no runner is coming for it, and it has not passed.

`count` gives the four counts of a list of tasks, and `cause` names the largest of them, which is
what slows the rows in check. Of two that are as large, a failing check comes first, since it waits
on a fix, then one that runs or waits, then one that passed, then a stacked row.
"""

from __future__ import annotations

from typing import Any

from jmerge import ready

STEP = "check"
FAILING, WAITING, PASSED, STACKED = "failing", "waiting", "passed", "stacked"
OUTCOMES = (FAILING, WAITING, PASSED, STACKED)
OUTCOME = {"failed": FAILING, "pending": WAITING, "none": WAITING, "passed": PASSED}
SHAPE = dict.fromkeys(OUTCOMES)
STACKED_CODES = frozenset(
    ready.code_of(reason)
    for reason in (ready.STACKED_ON, ready.STACKED_UNMOVED, ready.MERGES_AFTER, ready.CARRIES_AFTER)
)
STACKED_ON = "stacked on"


def stacked(task: dict[str, Any]) -> bool:
    """Whether the last line `jmerge` logged of the task says it merges after another row."""
    history = task.get("history") or [{"code": "", "reason": task.get("reason") or ""}]
    last = history[-1]
    code = last["code"] or ready.code_of(last["reason"])
    return code in STACKED_CODES or STACKED_ON in last["reason"]


def outcome(task: dict[str, Any]) -> str | None:
    """The outcome of a task's check, or None where it has none."""
    if stacked(task):
        return STACKED
    return OUTCOME.get(task.get("checks") or "")


def count(tasks: list[dict[str, Any]]) -> dict[str, int]:
    """How many of the tasks in check have each outcome."""
    found = [outcome(task) for task in tasks if task["step"] == STEP]
    return {one: found.count(one) for one in OUTCOMES}


def cause(counts: dict[str, int]) -> str | None:
    """The largest of the counts, the first of `OUTCOMES` of two that tie, or None where every
    count is 0."""
    largest = max(OUTCOMES, key=lambda one: counts[one])
    return largest if counts[largest] else None
