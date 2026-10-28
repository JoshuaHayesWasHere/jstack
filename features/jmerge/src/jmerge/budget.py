"""`budget` is the one reading of GitHub's API allowance, which `jmerge`, jbus and every thread
share: they all call GitHub with the one token `gh` holds, and GitHub gives that token so many
calls an hour.

`gh api rate_limit` says what is left, and asking it spends nothing, also once the allowance is
spent. GitHub keeps two windows that jstack spends: `core`, the REST calls of `gh api`, and
`graphql`, the calls of `gh pr list` and `gh pr view`. `parse` reads its answer.

When GitHub refuses a call for its rate limit, `gh` exits non-zero with a 403 or a 429 and says
`API rate limit exceeded`, or `secondary rate limit` for a burst, on stderr (`refused`). Such a
failure is not GitHub that cannot be read: `named` says the window, what is left of it, and when
it starts again, from `gh api rate_limit`. A secondary limit leaves the windows full, so `named`
says what it read and claims nothing about it being spent. jbus keeps its floor above this
(`jbus.budget`).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

WINDOWS = ("core", "graphql")
ASK = ["gh", "api", "rate_limit"]
REFUSED = "GitHub refused it for its API rate limit"
SPENT = "GitHub's API allowance is spent"
"""`REFUSED` starts the line for a call GitHub refused (`named`), and `SPENT` the line for a
window `gh api rate_limit` says has no call left (`spent`). A reader of a kept line tells either
by its start (`is_named`)."""

_LIMITED = re.compile(r"\brate limit\b|\bHTTP 429\b|\babuse detection\b", re.IGNORECASE)


@dataclass(frozen=True)
class Window:
    """What GitHub says is left of one window, and when the window starts again."""

    name: str
    remaining: int
    limit: int
    reset: datetime


@dataclass(frozen=True)
class Budget:
    """GitHub's answer to `gh api rate_limit`: each window jstack spends."""

    windows: tuple[Window, ...]

    @property
    def low(self) -> Window:
        """The window with the fewest calls left."""
        return min(self.windows, key=lambda one: one.remaining)

    @property
    def is_spent(self) -> bool:
        """Whether a window has no call left."""
        return self.low.remaining <= 0


def parse(text: str) -> Budget | None:
    """Return the budget that `gh api rate_limit` printed, or None where it is not one."""
    try:
        resources = json.loads(text)["resources"]
        windows = tuple(
            Window(
                name,
                int(resources[name]["remaining"]),
                int(resources[name]["limit"]),
                datetime.fromtimestamp(int(resources[name]["reset"]), UTC),
            )
            for name in WINDOWS
        )
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return None
    return Budget(windows)


def given(asked: subprocess.CompletedProcess[str]) -> Budget | None:
    """The budget in what a run of `ASK` gave, or None where it gave none."""
    return parse(asked.stdout) if asked.returncode == 0 else None


def at(when: datetime) -> str:
    """A reset time as every line about the budget says it."""
    return when.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def refused(stderr: str) -> bool:
    """Whether what `gh` said on stderr is GitHub refusing the call for its rate limit."""
    return bool(_LIMITED.search(stderr or ""))


def left(budget: Budget) -> str:
    """What is left of the lowest window, and when it starts again."""
    low = budget.low
    until = at(low.reset)
    return f"its {low.name} window has {low.remaining} of {low.limit} calls left until {until}"


def named(asked: subprocess.CompletedProcess[str]) -> str:
    """The line for a call GitHub refused for its rate limit, from what a run of `ASK` gave."""
    budget = given(asked)
    if budget is None:
        return f"{REFUSED}, and `gh api rate_limit` did not say when it starts again"
    return f"{REFUSED}: {left(budget)}"


def spent(budget: Budget) -> str:
    """The line for a budget with a window that has no call left, or nothing."""
    return f"{SPENT}: {left(budget)}" if budget.is_spent else ""


def is_named(text: str) -> bool:
    """Whether a line is one `named` or `spent` gave."""
    return text.startswith((REFUSED, SPENT))
