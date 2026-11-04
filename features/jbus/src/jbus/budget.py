"""`jbus budget`: whether a thread may call GitHub now. GitHub's API allowance, which jbus,
`jmerge` and every thread share, and the floor jbus keeps under it are `jsettings.budget`, read
through the one runner (`jsettings.proc`); this module re-exports them under their old names.

A pass of jbus reads the budget before it asks GitHub for its world (`jbus.watch.look`). When it
is held, the pass asks GitHub nothing and has no world, as when GitHub is silent, so no row
changes; `jmerge` still runs. `jbus flow --jobs` refuses a call per run that would take the
budget to the floor (`jbus.flow.records.affordable`). A thread runs `jbus budget` before a loop
of `gh` calls, with `--wait` to wait in its turn, and refuses while it ends 75 (`TEMPFAIL`). The
skills name each loop.

`jbus budget --callers` prints the calls to `gh` of the last hour by caller, from the line each
writes (`jsettings.proc.CALLS`), with how many of them failed.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jbus
from jbus import verbs
from jsettings import paths
from jsettings.budget import ASK as ASK
from jsettings.budget import FLOOR as FLOOR
from jsettings.budget import Ask as Ask
from jsettings.budget import Budget as Budget
from jsettings.budget import at as at
from jsettings.budget import held, read
from jsettings.budget import parse as parse
from jsettings.proc import CALLS
from jsettings.proc import TIMEOUT as TIMEOUT
from jsettings.proc import ask as ask

TEMPFAIL = 75
AGAIN = 30


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
    parser.add_argument(
        "--callers",
        action="store_true",
        help="print the gh calls of the last hour by caller, from jbus's log of them",
    )


def _budget(args: argparse.Namespace, _: jbus.Config | None) -> int:
    """Print whether a thread may call GitHub now: `ok` and 0, or `held` and 75. With `--wait`,
    a held budget is asked again until it is above the floor or the time is up."""
    if args.callers:
        print(callers(paths.jbus_state_dir(), datetime.now(UTC) - timedelta(hours=1)))
        return 0
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


def calls(state: Path, since: datetime) -> list[dict]:
    """The logged gh calls that ended at or after `since`, from the log and the one before it."""
    found = []
    for path in (state / f"{Path(CALLS).stem}.old.jsonl", state / CALLS):
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                call = json.loads(line)
                if datetime.fromisoformat(call["at"]) >= since:
                    found.append(call)
            except (ValueError, KeyError, TypeError):
                continue
    return found


def callers(state: Path, since: datetime) -> str:
    """The gh calls since `since` by caller, the most first, each with how many failed."""
    found = calls(state, since)
    count = Counter(call.get("caller", "?") for call in found)
    failed = Counter(call.get("caller", "?") for call in found if call.get("status"))
    lines = [f"{len(found)} gh calls since {since:%Y-%m-%d %H:%M} UTC, by caller:"]
    for name, n in count.most_common():
        lines.append(f"{n:6}  {name} ({failed[name]} failed)")
    return "\n".join(lines)


VERBS = (
    verbs.Verb(
        "budget",
        "whether GitHub's API budget is above the floor: ok and 0, or held and 75",
        _arguments,
        _budget,
        config=False,
    ),
)
