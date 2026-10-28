"""What the check of a row in check did: it failed, it runs or waits for a runner, or it passed and
the row waits for `jmerge`.

A row is in check where the last pass put it on the step `check`. Its outcome comes from the
row's `checks`, the one word `jmerge --checks` reads from the latest run of each check of the pull
request (`jmerge.checks.checks`), which the pass writes beside the row (`watch.checks`). So a red
lint beside a check that still runs is a failing row, as it is to `jmerge`. `OUTCOME` is the one
table of the words: `failed`, which also holds a check that never started beside checks that ran;
`pending` and `none`, where no check has answered yet; and `passed`. A row whose word is `unrun`
(every check skipped at its head), `draft` or none at all is in check and has none of the three
outcomes: no runner is coming for it, and it has not passed.

`count` gives the three counts of a list of tasks, and `cause` names the largest of them, which is
what slows the rows in check. Of two that are as large, a failing check comes first, since it waits
on a fix, and one that runs or waits next.
"""

from __future__ import annotations

from typing import Any

STEP = "check"
FAILING, WAITING, PASSED = "failing", "waiting", "passed"
OUTCOMES = (FAILING, WAITING, PASSED)
OUTCOME = {"failed": FAILING, "pending": WAITING, "none": WAITING, "passed": PASSED}
SHAPE = dict.fromkeys(OUTCOMES)


def outcome(task: dict[str, Any]) -> str | None:
    """The outcome of a task's check, or None where its word has none."""
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
