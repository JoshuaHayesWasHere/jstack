"""A pass whose GitHub budget is at or under its floor launches nothing (`jbus.watch.look`), and
this module says so where the user and the home read.

Each approved row at `queued` that has no other reason to wait, which the pass would otherwise
launch, gets the why `GitHub's budget: <left> of <limit> calls, launches wait until <reset>`,
the reset in the user's time (`hold`). The pass changes no other column of the table, so no row's
status moves while GitHub goes unasked. The first pass that reads the budget above the floor
judges the table as usual, and the row launches or takes its own reason.

The hold is kept in `budget-hold.json` of the project's state, with the pass it began in, and
goes on the first pass that reads the budget above the floor; a pass that could not read the
budget keeps it as it was. `jbus needs` lists it as one item for the whole project once it has
lasted over `LISTED` (`needed`), whatever the rows it holds, and not after its reset.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import jsettings
from jbus import queue, read_json, verbs, write_json
from jbus.passes import Pass

if TYPE_CHECKING:
    from jbus.poll import Half

FILE = "budget-hold.json"
PREFIX = "GitHub's budget: "
LISTED = timedelta(minutes=10)


def why(run: Pass, left: int, limit: int, reset: datetime) -> str:
    """The why of a row the budget holds."""
    until = run.user.stamp(reset)
    return f"{PREFIX}{left} of {limit} calls, launches wait until {until}"


def held_why(text: str) -> bool:
    """Whether a row's why is one `why` gave."""
    return text.startswith(PREFIX)


def _waits(row: queue.Row) -> bool:
    """Whether the pass would launch the row but for the budget: approved, queued, and with no
    other reason to wait than the budget."""
    said = str(row.get("why") or "")
    return (
        bool(row.get("approved")) and row.get("status") == "queued" and (not said or held_why(said))
    )


def hold(half: Half) -> None:
    """Keep the budget's hold, and write its why on each row it holds (`_waits`)."""
    run, seen = half.run, half.seen
    path = run.state / FILE
    if seen.left is None:
        return
    if not seen.held:
        path.unlink(missing_ok=True)
        return
    low = seen.left.low
    said = why(run, low.remaining, low.limit, low.reset)
    kept = read_json(path, {})
    since = kept.get("since") if isinstance(kept, dict) else None
    record = {
        "since": since or run.now.isoformat(),
        "reset": low.reset.isoformat(),
        "why": said,
    }
    if record != kept:
        write_json(path, record)
    if half.rows is None or seen.world is not None:
        return

    def facts(row: queue.Row) -> queue.Row:
        same = {column: row.get(column, "") for column in queue.SEEN}
        same["status"] = row.get("status") or "queued"
        return {**same, "why": said if _waits(row) else row.get("why", "")}

    at = jsettings.stamp(run.now)
    half.table, _ = queue.derive(run.state, facts, run.user.stamp(run.now), at)


def needed(run: Pass) -> str:
    """The hold's why, where it has lasted over `LISTED` and its reset is still to come, else
    nothing."""
    kept = read_json(run.state / FILE, {})
    try:
        since = datetime.fromisoformat(kept["since"])
        reset = datetime.fromisoformat(kept["reset"])
        said = str(kept["why"])
    except (KeyError, TypeError, ValueError):
        return ""
    return said if run.now - since > LISTED and run.now < reset else ""


STEPS = (verbs.Step("derive", 25, "budgethold.hold", hold, ("sight",)),)
