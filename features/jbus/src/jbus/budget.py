"""`budget` is the floor jbus keeps under GitHub's API budget, which jbus and every thread share:
they all call GitHub with the one token `gh` holds, and GitHub gives that token so many calls an
hour.

`gh api rate_limit` says what is left, and asking it spends nothing. GitHub keeps two windows
that jbus spends: `core`, the REST calls of `gh api`, and `graphql`, the calls of `gh pr list`
and `gh pr view`. `jmerge.budget` is the one reading of that answer, which `jmerge` shares to
name a call GitHub refused for its rate limit. The budget is held when either window has `FLOOR`
calls or fewer left, and when GitHub gave no answer, since then nobody can tell. What is under
the floor is kept for what must be asked: `jmerge`'s merge and the reads it makes.

A pass of jbus reads the budget before it asks GitHub for its world (`jbus.watch.look`). When it
is held, the pass asks GitHub nothing and has no world, as when GitHub is silent, so no row
changes; `jmerge` still runs. `jbus flow --jobs` refuses a call per run that would take the
budget to the floor (`jbus.flow.records.affordable`). A thread runs `jbus budget` before a loop
of `gh` calls, with `--wait` to wait in its turn, and refuses while it ends 75 (`TEMPFAIL`). The
skills name each loop.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Callable

import jbus
from jbus import verbs
from jmerge.budget import ASK, Budget, at, parse

FLOOR = 1000
"""The calls kept in each window for what must be asked: a fifth of the 5,000 an hour that GitHub
gives a signed-in user."""
TEMPFAIL = 75
TIMEOUT = 30
AGAIN = 30

Ask = Callable[[list[str]], "str | None"]


def ask(command: list[str]) -> str | None:
    """Run a command and return what it printed, or None where it failed."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def read(asked: Ask = ask) -> Budget | None:
    """Ask GitHub what is left of the budget. None is no answer."""
    said = asked(ASK)
    return parse(said) if said is not None else None


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


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--calls", type=int, default=0, help="the calls the caller is about to make (default: 0)"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SECONDS",
        help="while held, ask again every 30 seconds for up to this long (default: 0)",
    )


def _budget(args: argparse.Namespace, _: jbus.Config | None) -> int:
    """Print whether a thread may call GitHub now: `ok` and 0, or `held` and 75. With `--wait`,
    a held budget is asked again until it is above the floor or the time is up."""
    until = time.monotonic() + max(args.wait, 0)
    while True:
        budget = read()
        why = held(budget, max(args.calls, 0))
        if budget is not None and not why:
            low = budget.low
            print(f"ok: GitHub's {low.name} budget has {low.remaining} calls left, floor {FLOOR}")
            return 0
        if time.monotonic() >= until:
            print(f"held: {why}: make no call to GitHub that can wait")
            return TEMPFAIL
        time.sleep(min(AGAIN, max(until - time.monotonic(), 0)))


VERBS = (
    verbs.Verb(
        "budget",
        "whether GitHub's API budget is above the floor: ok and 0, or held and 75",
        _arguments,
        _budget,
        config=False,
    ),
)
