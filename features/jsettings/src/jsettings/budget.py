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
says what it read and claims nothing about it being spent.

The budget is held when either window has `FLOOR` calls or fewer left, and when GitHub gave no
answer, since then nobody can tell (`held`). What is under the floor is kept for what must be
asked: `jmerge`'s merge and the reads it makes. `read` asks for it through the one runner
(`jsettings.proc`), and `jbus budget` is the verb a thread runs before a loop of `gh` calls.

Every response of GitHub's says what is left of the window it counts against, and the runner logs
it with each `gh` call (`proc.CALLS`). `logged` reads each window's `remaining` from the lines of
that log of the last `WITHIN` seconds, and asks `gh api rate_limit` only where a window has none,
once for every process that reads it then. GitHub keeps two counts of one window, which start
again at different times and on 2026-11-08 stood up to 2,900 calls apart; a response gives either
(`/actions/` endpoints the other one 43% of the time, `/rate_limit` itself 0.6%). So `logged`
takes the lowest count of the last `WITHIN` seconds: never later to hold than either count. The
log has no window's limit nor its reset, so `logged` keeps those from the last answer it asked for
(`KEPT`), and asks again once that window has started again.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsettings import proc

WINDOWS = ("core", "graphql")
ASK = ["gh", "api", "rate_limit"]
REFUSED = "GitHub refused it for its API rate limit"
SPENT = "GitHub's API allowance is spent"
"""`REFUSED` starts the line for a call GitHub refused (`named`), and `SPENT` the line for a
window `gh api rate_limit` says has no call left (`spent`). A reader of a kept line tells either
by its start (`is_named`)."""

FLOOR = 1000
"""The calls kept in each window for what must be asked: a fifth of the 5,000 an hour that GitHub
gives a signed-in user."""

WITHIN = 60
"""The seconds a logged `remaining` stands for its window before `logged` asks GitHub again."""
KEPT = "gh-rate-limit.json"
"""The last answer of `gh api rate_limit` that `logged` asked for, under jbus's state."""
CHUNK = 64 * 2**10
"""The bytes of the log `logged` reads at a time, from its end back."""

Ask = Callable[[list[str]], "str | None"]

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


def read(asked: Ask = proc.ask) -> Budget | None:
    """Ask GitHub what is left of the budget. None is no answer."""
    said = asked(ASK)
    return parse(said) if said is not None else None


def logged(state: Path, within: float = WITHIN, asked: Ask = proc.ask) -> Budget | None:
    """What is left of the budget, from what GitHub said in the last `within` seconds: for each
    window the lowest count of the lines of `proc.CALLS` under `state` and of the kept answer
    (`KEPT`). Where a window has neither, or the kept answer's window has started again, it asks
    with `read`, once: a reader in another thread or process that finds the ask going waits for
    its answer, and takes it. None is no answer."""
    found = _logged(state, within)
    if found is not None:
        return found
    with _locked(state):
        found = _logged(state, within)
        if found is not None:
            return found
        answer = read(asked)
        if answer is not None:
            _keep(state, answer)
        return answer


def _logged(state: Path, within: float) -> Budget | None:
    now = datetime.now(UTC)
    since = now - timedelta(seconds=within)
    try:
        kept = json.loads((state / KEPT).read_text())
        at = datetime.fromisoformat(kept["at"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    budget = parse(json.dumps(kept))
    if budget is None or any(one.reset <= now for one in budget.windows):
        return None
    seen = _lowest(state / proc.CALLS, since)
    if at >= since:
        seen = {
            one.name: min(one.remaining, seen.get(one.name, one.remaining))
            for one in budget.windows
        }
    if len(seen) < len(WINDOWS):
        return None
    return Budget(tuple(replace(one, remaining=seen[one.name]) for one in budget.windows))


@contextlib.contextmanager
def _locked(state: Path) -> Iterator[None]:
    """Hold the lock of `KEPT` while the block runs. Where it cannot be taken, the block runs
    without it: a read that cannot be shared is still a read."""
    with contextlib.ExitStack() as held:
        try:
            state.mkdir(parents=True, exist_ok=True)
            fcntl.flock(held.enter_context(open(state / f".{KEPT}.lock", "a")), fcntl.LOCK_EX)
        except OSError:
            pass
        yield


def _keep(state: Path, budget: Budget) -> None:
    """Write the answer, with when it was given, in `gh api rate_limit`'s own shape, in one
    rename, so that a reader in another process never reads half of it. A state that cannot be
    written costs the read nothing: the next one asks again."""
    resources = {
        one.name: {
            "remaining": one.remaining,
            "limit": one.limit,
            "reset": int(one.reset.timestamp()),
        }
        for one in budget.windows
    }
    at = datetime.now(UTC).isoformat()
    try:
        made, name = tempfile.mkstemp(dir=state, prefix=f".{KEPT}.")
        with os.fdopen(made, "w") as file:
            json.dump({"at": at, "resources": resources}, file)
        os.replace(name, state / KEPT)
    except OSError:
        return


def _lowest(path: Path, since: datetime) -> dict[str, int]:
    """The lowest `remaining` of each of `WINDOWS` in the lines of the log at `path` at or after
    `since`, read from the end back to the first line before it."""
    found: dict[str, int] = {}
    with contextlib.ExitStack() as opened:
        try:
            file = opened.enter_context(open(path, "rb"))
        except OSError:
            return found
        end = file.seek(0, os.SEEK_END)
        left = b""
        while end > 0:
            start = max(0, end - CHUNK)
            file.seek(start)
            lines = (file.read(end - start) + left).split(b"\n")
            left = lines.pop(0) if start > 0 else b""
            for line in reversed(lines):
                if not _take(line, since, found):
                    return found
            end = start
    return found


def _take(line: bytes, since: datetime, found: dict[str, int]) -> bool:
    """Keep the line's `remaining` for its window where it is the lowest yet, and return whether
    the line is at or after `since`, so that the lines before it are read too."""
    try:
        one = json.loads(line)
        if datetime.fromisoformat(one["at"]) < since:
            return False
    except (ValueError, TypeError, KeyError):
        return True
    resource, remaining = one.get("resource"), one.get("remaining")
    if resource in WINDOWS and isinstance(remaining, int):
        found[resource] = min(remaining, found.get(resource, remaining))
    return True


def held(budget: Budget | None, calls: int = 0) -> str:
    """Return why `calls` more calls must wait, or nothing when the budget leaves them more than
    `FLOOR` in every window."""
    if budget is None:
        return "GitHub did not say what is left of its API budget"
    low = budget.low
    if low.remaining - calls > FLOOR:
        return ""
    more = f", and {calls} calls would take it to {low.remaining - calls}" if calls else ""
    return (
        f"GitHub's {low.name} budget has {low.remaining} of {low.limit} calls left{more}, "
        f"at or under the floor of {FLOOR} kept for merges, until {at(low.reset)}"
    )
