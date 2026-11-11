"""File one row for a test that main's ledger of reds calls a flake twice in seven days.

`mainmoved.tell` writes a line to `main-reds.jsonl` for each red tip of main, with the tests that
failed there and its verdict (`mainmoved.red_line`). This step reads that verdict and works out
no flake rule of its own. Where one test is under `failed` in lines of the verdict `flake` of two
spells of a red main, each at its first such line, no more than `WINDOW` apart, and the later of
them within `WINDOW` of the pass, it writes `tasks/flake-<name>.md` and queues it with no go, as jbus's pass. The next pass approves it
by the follow-up rule, since jbus filed it (`queue.filed`). One flake is noise: two timing flakes
of one week were two different tests (the scout po-worse-change-failure's Report).

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
    """Return each test that failed under the verdict `flake`, with each red it failed at, the
    oldest first and one a spell: the later tips of a spell take its first line's verdict
    (`mainmoved.red_line`), so a spell is one flake however many tips it has. A line from before
    the ledger kept the green tip a red came `after` is a spell of its own."""
    seen: dict[str, dict[str, Seen]] = {}
    for line in lines:
        if line.get("verdict") != str(mainmoved.Verdict.FLAKE):
            continue
        at = datetime.fromisoformat(str(line["at"]))
        sha = str(line.get("sha") or "")
        spell = f"after {line['after']}" if "after" in line else sha
        for failed in line.get("failed") or []:
            seen.setdefault(test_of(str(failed)), {}).setdefault(spell, (at, sha))
    return {test: sorted(spells.values()) for test, spells in seen.items()}


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
    """Write and queue the row `name` where the queue has none, and return whether it is filed:
    removed, already in the queue, or queued now."""
    if name in run.removed or queue.fresh(run.state, name) is not None:
        return True
    text = brief(name, test, pair)
    (run.home / "tasks").mkdir(parents=True, exist_ok=True)
    (run.home / "tasks" / f"{name}.md").write_text(text)
    try:
        queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)
    except (Refused, queue.Unparsable) as refused:
        run.condition(name, f"its brief was not queued: {refused}")
        return False
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
