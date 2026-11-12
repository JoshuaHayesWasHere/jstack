"""File one row for a test that main's ledger of reds calls a flake twice in seven days.

`mainmoved.tell` writes a line to `main-reds.jsonl` for each red tip of main, with the tests that
failed there (`mainmoved.red_line`), and one more when the spell ends, with its cause
(`mainmoved.closing_line`). A flake is a spell that went green with no fix (`mainmoved.NO_FIX`):
one run cannot tell a load flake from a break, and the verdict a red tip got when it was judged
called real faults flakes (jstack's 8b6c51f76 and 54d9f0055) and flakes faults (spells 44 and
45). This step reads that cause and works out no flake rule of its own. Where one test failed in
two spells that went green with no fix, their first red tips no more than `WINDOW` apart, and the
later of them within `WINDOW` of the pass, it queues `flake-<name>` with no go, as jbus's pass,
and then writes `tasks/flake-<name>.md`, so a pass that stops between the two leaves a row, never
a brief that no row names. The next pass approves it by the follow-up rule, since jbus filed it
(`queue.filed`). One flake is noise: two timing flakes of one week were two different tests (the
scout po-worse-change-failure's Report).

A test gets one row, ever. `flake-rows.json` in the project's state keeps each test it filed, with
the row's slug, so a third flake, a pass run again, or a flake after the row merged files no
other. Where a pass stopped after it queued the row and before it kept it, the next one finds the
row in the queue and keeps it. A removed row is kept and never filed again. Where the queue
refuses the brief, nothing is kept, and the refusal is a condition.

A test is the id the ledger names less its parameters, so the cases of one parametrized test are
one test. `<name>` is the test function's name, with `-` for each run of other characters.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from jbus import Refused, mainmoved, queue, read_json, verbs, watch, write_json
from jbus.ci.ledger import read as reds

if TYPE_CHECKING:
    from jbus.passes import Pass
    from jbus.poll import Half

PREFIX = "flake-"
WINDOW = timedelta(days=7)
LEDGER = "flake-rows.json"

Seen = tuple[datetime, str]
"""When the pass judged a red tip, and its commit."""


def test_of(failed: str) -> str:
    """Return the test a failed id names: the id less its parameters."""
    return re.sub(r"\[.*\]$", "", failed)


def slug(test: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "-", test.rpartition("::")[2].lower()).strip("-")
    return f"{PREFIX}{name}"


def flakes(lines: list[dict[str, Any]]) -> dict[str, list[Seen]]:
    """Return each test that failed in a spell that went green with no fix, with the first red tip
    of each such spell, the oldest first: a spell is one flake however many tips it has. A spell
    still red, or one from before the ledger kept the green tip a red came `after`, has no closing
    line, and counts for nothing."""
    unfixed = {line.get("sha") for line in lines if line.get("cause") == mainmoved.NO_FIX}
    seen: dict[str, list[Seen]] = {}
    for first in lines:
        if "verdict" not in first or "after" not in first or first.get("sha") not in unfixed:
            continue
        opened = mainmoved.spell(lines, str(first["after"]))
        red = (datetime.fromisoformat(str(first["at"])), str(first["sha"]))
        tests = {test_of(str(failed)) for one in opened for failed in one.get("failed") or []}
        for test in tests:
            seen.setdefault(test, []).append(red)
    return {test: sorted(reds) for test, reds in seen.items()}


def twice(seen: list[Seen], now: datetime) -> tuple[Seen, Seen] | None:
    """Return the latest two flakes no more than `WINDOW` apart, the later one within `WINDOW`
    of `now`, or None where there are none."""
    pairs = [
        (first, then)
        for first, then in pairwise(seen)
        if then[0] - first[0] <= WINDOW and now - then[0] <= WINDOW
    ]
    return pairs[-1] if pairs else None


def brief(name: str, test: str, pair: tuple[Seen, Seen]) -> str:
    """Return the row's brief, in the shape `watch.fix_brief` gives a red's fix."""
    reds_ = " and ".join(f"{sha[:12]} ({at.isoformat()})" for at, sha in pair)
    return watch.fix_brief(
        f"{name}: `{test}` flaked on main twice in seven days",
        f'"`{test}` failed as a flake on main at {reds_}" (jbus, the ledger of main\'s reds, '
        f"`{mainmoved.REDS}`)",
        "a flake turns main red with no fault behind it, which holds every merge and sends a "
        "crew after a cause that is not there, and two in seven days says it will again",
        [
            f"- `{test}` passes on main however its runs are timed or ordered, and the Result "
            "names what made it flake, with its evidence",
            "- a test, or the fixed test itself, fails on the cause before the fix and passes "
            "after it",
        ],
        f"`uv run pytest -q {test.partition('::')[0]}` passes, and CI's check on main passes at "
        "the commit that merges the fix",
        f"main's ledger, which called `{test}` a flake twice in seven days,",
        [],
        [
            f"- main's red at {sha}, judged {at.isoformat()}: `{test}` failed as a flake"
            for at, sha in pair
        ],
        files=[test.partition("::")[0]],
        nowhere="`.`",
    )


def file(run: Pass, name: str, test: str, pair: tuple[Seen, Seen]) -> bool:
    """Queue the row `name` where the queue has none, then write its brief's copy to `tasks/`
    (`watch.copy_brief`), and return whether it is filed: removed, already in the queue, or
    queued now."""
    if name in run.removed or queue.fresh(run.state, name) is not None:
        return True
    text = brief(name, test, pair)
    try:
        queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)
    except (Refused, queue.Unparsable) as refused:
        run.condition(name, f"its brief was not queued: {refused}")
        watch.copy_brief(run, name, text)
        return False
    watch.copy_brief(run, name, text)
    run.find(name, "retro", f"retro {name}: `{test}` flaked on main twice in seven days")
    return True


def keep(half: Half) -> None:
    """File a row for each test the ledger calls a flake twice in seven days that has none."""
    run = half.run
    kept: dict[str, Any] = read_json(run.state / LEDGER, {"filed": {}})
    for test, seen in sorted(flakes(reds(run.state / mainmoved.REDS)).items()):
        if test in kept["filed"] or (pair := twice(seen, run.now)) is None:
            continue
        name = slug(test)
        if file(run, name, test, pair):
            kept["filed"][test] = name
            write_json(run.state / LEDGER, kept)


STEPS = (verbs.Step("close", 56, "flakerow.keep", keep, ("sight",)),)
