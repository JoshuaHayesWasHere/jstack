"""A row's status moves only as `queue.MOVES` declares, and a pass marks every other move.

No verb moves a row: each pass works its status out again from seven facets (`work.status`).
The walk changes one facet of every set of facts there is and asserts that each move of status
it makes is in the table, or is one this file names with the reason the table leaves it out. So
a new status, or a projection that makes a new move, fails here until somebody judges it.
The pass tests run the real pass against the faked T3 Code and GitHub of `test_jbus_queue.py`.
"""

import dataclasses
import json
import re
from pathlib import Path

from jbus import queue, work
from test_jbus_kitchen import RESULT
from test_jbus_queue import add, rows, scene

DOC = Path(__file__).parents[1] / "docs" / "jbus" / "row-moves.md"


def _pairs(reason: str, **moves: str) -> dict[tuple[str, str], str]:
    """Each move from a status (the keyword) to each status its words name, with `reason`."""
    return {(was, now): reason for was, nows in moves.items() for now in nows.split()}


FINAL = (
    "a final row stays final: jmerge (`rows.py`) and `watch.final` read a row that leaves it "
    "as not final"
)
PR_LOST = (
    "an open pull request ends merged, closed or with a Result that owes none: a row with a pull "
    "request is never queued but by a pull request the pass read in neither of GitHub's lists"
)
SWAPPED = (
    "both are final, and a merged row stays merged: a merged pull request no list holds is read "
    "in neither of GitHub's lists"
)
NO_LAUNCH = (
    "a row has a thread, a Result or a pull request only once a launch record names it, and keeps "
    "the record: a pass that sees one with no record, or a record go, lost the launch record"
)

NAMED = {
    **_pairs(
        FINAL,
        merged="queued launched running waiting pr failed stale gate left",
        done="queued launched running waiting pr failed stale gate left",
    ),
    **_pairs(SWAPPED, merged="done"),
    **_pairs(PR_LOST, pr="queued"),
    **_pairs(
        NO_LAUNCH,
        queued="running waiting stale failed done left pr merged",
        launched="queued",
        running="queued",
        waiting="queued",
        stale="queued",
        failed="queued",
        left="queued",
    ),
}
"""Each move of status the walk makes that `queue.MOVES` does not hold, with why: each leaves a
final row, whose status `derive` keeps (`work.kept`), so no pass writes it, or is a fault, which a
pass marks. `RowLife.tla` makes none of them, since its row's facts change only after its launch
and its launch record stays."""


def _walked() -> dict[tuple[str, str], str]:
    """Every move of status that one changed facet makes, with one such change. Both sources
    answered: a pass that did not hear one keeps the last state, which is no change of facts.
    A row is never `removed` by a pass: `remove` takes it out and writes its own line."""
    statuses = {
        facts: work.status(work.judge(facts))
        for facts in work.every()
        if facts.answered == work.Answered.BOTH and facts.row != work.Row.REMOVED
    }
    moves = {}
    for facts, was in statuses.items():
        for name, values in work.FACETS.items():
            for value in values:
                other = dataclasses.replace(facts, **{name: value})
                now = statuses.get(other, was)
                if now != was:
                    moves.setdefault((was, now), f"{name}: {getattr(facts, name)} to {value}")
    return moves


def test_every_move_one_changed_fact_makes_is_in_the_table_or_named_with_its_reason():
    walked = _walked()
    unjudged = {move: change for move, change in walked.items() if move not in queue.MOVES}
    assert {move: change for move, change in unjudged.items() if move not in NAMED} == {}
    assert set(NAMED) & set(queue.MOVES) == set()
    assert set(NAMED) - set(walked) == set()


def test_the_table_holds_the_legal_moves_and_none_of_the_faults():
    removals = {(was, "removed") for was in ("queued", "left", "pr")}
    assert {move for move in queue.MOVES if move[1] != "removed"} <= set(_walked())
    assert removals <= set(queue.MOVES)
    faults = {("done", "pr"), ("merged", "gate"), ("done", "gate")}
    assert faults & set(queue.MOVES) == set()


def _moved(kitchen, was, status, brief=""):
    """Run a pass on a row whose status the table says is `was`, and the facts make `status`."""
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", brief)
    scene(kitchen, status)
    table = list(rows(kitchen).values())
    table[0]["status"] = was
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    kitchen.poll()
    lines = (kitchen.state / "transitions.jsonl").read_text().splitlines()
    return rows(kitchen)["alpha"]["status"], [json.loads(line) for line in lines][-1]


def test_a_pass_marks_a_move_the_table_does_not_hold_and_still_writes_the_status(kitchen):
    """The move the table lacks here is from a status no table names, as a row written by hand
    or by an older jbus has."""
    status, line = _moved(kitchen, "parked", "running")
    assert status == "running"
    assert {key: line[key] for key in ("slug", "from", "to", "legal")} == {
        "slug": "alpha",
        "from": "parked",
        "to": "running",
        "legal": False,
    }
    assert kitchen.lines("illegal-move") == ["illegal-move alpha: parked to running"]


def test_a_pass_leaves_a_move_the_table_holds_unmarked(kitchen):
    status, line = _moved(kitchen, "pr", "merged", RESULT)
    assert status == "merged"
    assert (line["from"], line["to"]) == ("pr", "merged")
    assert "legal" not in line
    assert kitchen.lines("illegal-move") == []


def test_the_docs_list_each_move_of_the_table_with_its_cause():
    listed = re.findall(r"^\| `(\w+)` \| `(\w+)` \| (.+) \|$", DOC.read_text(), re.M)
    assert {(was, now): cause for was, now, cause in listed} == queue.MOVES
    assert len(listed) == len(queue.MOVES)
