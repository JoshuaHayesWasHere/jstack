"""A row whose merge a revert jbus opened took back is open again once that revert merges, so its
redo is reviewed before its pull request opens and merged as any row's (`jbus.reverts.reland`).

On 2026-11-13 #1869 (jgauge-short-cut-orphans) merged, jbus reverted it in #1870, and the crew
pushed the redo. The row stayed `merged`, so jbus launched no review of the redo and jmerge held
#1872 as a row that is over ("its queue row is merged, and a row that is over waits for no merge:
accept it to merge it") until the root accepted it by hand.

Like `test_jbus_prereview.py`, the tests run the real pass against the kitchen's fakes, with a real
origin, over a row jbus launched, and read the reason jmerge gives a pull request from the queue
the pass wrote (`jmerge.rows.short`). The last replays the row's `transitions.jsonl` over
RowLife's graph (`features/jbus/spec/RowLife.tla`)."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import queue
from jmerge import ready
from jmerge import reverts as kept
from jmerge import rows as merge_rows
from test_jbus_kitchen import NOW
from test_jbus_prereview import proof, pushed_branch, reviewers
from test_jbus_queue import add, rows
from test_rowlife_replay import replay

MERGE = "a" * 40
"""The merge commit of alpha's first pull request, #7, the red tip its revert reverts."""
REVERT = "b" * 40
REDO = "f" * 40


def url(number):
    return f"https://example.test/pull/{number}"


def status(kitchen):
    return rows(kitchen)["alpha"]["status"]


def merged_row(kitchen):
    """alpha, launched, whose crew wrote its Result naming #7 and ended its turn, and #7 merged
    at `MERGE`. Returns the crew's thread and the brief's path."""
    add(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(minutes=30))
    (thread,) = kitchen.t3.threads
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(
        path.read_text() + "\n## Result\nStatus: done\nDone when: holds\nProof:\n- a test\n"
        f"Branch: alpha   Pull request: {url(7)}\nChanged: a doc\nSteers: none\nLeft: none\n"
    )
    thread.update(status="completed", latestRunId="run-1")
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, MERGE, ago=timedelta(minutes=25))])
    kitchen.poll(NOW - timedelta(minutes=27))
    assert status(kitchen) == "merged"
    return thread, path


def reverted(kitchen):
    """The record jbus keeps once it opened the revert of #7 (`reverts._own`): #9 on the branch
    GitHub names, open."""
    record = kept.Revert(MERGE, "alpha", "revert-7-alpha", "e" * 40, url(9))
    jbus.write_json(
        kitchen.state / kept.NAME, {MERGE: {**kept.record(record), "holders": ["main"]}}
    )
    kitchen.brief(
        "revert-7-alpha",
        f"Home: uncategorized\n\n## Result\nStatus: done\n"
        f"Branch: revert-7-alpha   Pull request: {url(9)}\n",
    )
    kitchen.set("open.json", [kitchen.opened("revert-7-alpha", 9)])


def revert_merges(kitchen):
    kitchen.set("open.json", [])
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    landed = kitchen.merged("revert-7-alpha", 9, REVERT, ago=timedelta(minutes=5))
    kitchen.set("merged.json", [*merged, landed])


def told(kitchen, thread):
    """The messages jbus sent the crew's thread that name the revert, #9."""
    sent = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    return [
        one for one in sent if one["threadId"] == thread["threadId"] and url(9) in one["message"]
    ]


def jmerge_says(kitchen, slug="alpha"):
    """What jmerge's queue rule says of the slug's pull request, read from the queue the pass
    wrote and the brief jbus stores, as `jmerge` reads both."""
    stored = (kitchen.state / "briefs" / f"{slug}.md").read_text()
    return merge_rows.short(list(rows(kitchen).values()), slug, brief=stored)


def test_a_row_whose_revert_merged_opens_again_and_its_redo_gets_its_review_and_no_row_over_hold(
    kitchen,
):
    """Once #9 merged, the row keeps #7 in its `reverted` column, and `jbus.watch.unlanded` reads
    #7 as no merge of the row's, so the redo #10 goes the way of any row's pull request."""
    thread, path = merged_row(kitchen)
    reverted(kitchen)
    kitchen.poll(NOW - timedelta(minutes=24))
    assert told(kitchen, thread), "jbus tells the culprit's crew of its revert"
    thread.update(status="completed", settled=False, archived=False, latestRunId="run-2")
    assert status(kitchen) == "merged"
    revert_merges(kitchen)
    kitchen.poll(NOW - timedelta(minutes=3))

    assert status(kitchen) not in ("merged", "done")
    assert rows(kitchen)["alpha"]["pr"] == ""
    assert rows(kitchen)["alpha"][queue.REVERTED] == url(7)
    assert kitchen.lines("reland") == [
        f"reland alpha: its revert {url(9)} merged, so the row is open for its redo"
    ]

    tree, head = pushed_branch(kitchen)
    thread.update(settled=False, archived=False, latestRunId="run-3", worktreePath=str(tree))
    path.write_text(path.read_text() + proof(head))
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (launched,) = reviewers(kitchen)
    assert launched["title"] == "review: alpha, 1"
    assert status(kitchen) == "running"

    kitchen.set("open.json", [kitchen.opened("alpha", 10)])
    path.write_text(
        path.read_text() + "\n## Result, follow-up (2026-11-13, the redo's pull request)\n"
        f"Status: done\nBranch: alpha   Pull request: {url(10)}\nLeft: none\n"
    )
    kitchen.poll(NOW + timedelta(minutes=6))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("pr", "#10")
    said = jmerge_says(kitchen)
    assert ready.code_of(said) != ready.ROW_OVER.code, said
    assert said == ""

    kitchen.set("open.json", [])
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    kitchen.set("merged.json", [*merged, kitchen.merged("alpha", 10, REDO, ago=timedelta(0))])
    kitchen.poll(NOW + timedelta(minutes=9))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#10")


@pytest.mark.parametrize("revert", ["open", "none"], ids=["revert not merged", "never reverted"])
def test_a_merged_row_keeps_its_status_while_no_revert_of_it_merged(kitchen, revert):
    merged_row(kitchen)
    if revert == "open":
        reverted(kitchen)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#7")
    assert kitchen.lines("reland") == []
    assert ready.code_of(jmerge_says(kitchen)) == ready.ROW_OVER.code


def test_a_revert_that_merged_after_a_redo_merged_keeps_the_redo(kitchen):
    """The record's red tip is #7's merge commit: once the redo #10 is the row's merge, a revert of
    #7 that merges late takes nothing back."""
    merged_row(kitchen)
    reverted(kitchen)
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    kitchen.set("merged.json", [*merged, kitchen.merged("alpha", 10, REDO, ago=timedelta(0))])
    kitchen.poll()
    revert_merges(kitchen)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#10")
    assert kitchen.lines("reland") == []


def test_the_reland_and_the_redo_replay_as_steps_of_rowlife(kitchen, capsys):
    """The row's whole life, its merge, the reland and the redo's merge, is a chain of RowLife's
    steps: the reland's own line reads as `Reland`, and no pass's line misses."""
    test_a_row_whose_revert_merged_opens_again_and_its_redo_gets_its_review_and_no_row_over_hold(
        kitchen
    )
    log = kitchen.state / "transitions.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    (moved,) = [line for line in lines if line.get("reverted")]
    assert (moved["from"], moved["to"], moved["reverted"]) == ("merged", "left", url(9))
    code, said = replay(log, capsys)
    assert (code, said) == (0, [f"{len(lines)} lines, {len(lines)} matched, 0 matched no step"])
