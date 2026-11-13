"""A row whose merge a revert jbus opened took back is open again once that revert merges, so its
redo is reviewed before its pull request opens and merged as any row's (`jbus.reverts.reland`).

On 2026-11-13 #1869 (jgauge-short-cut-orphans) merged, jbus reverted it in #1870, and the crew
pushed the redo. The row stayed `merged`, so jbus launched no review of the redo and jmerge held
#1872 as a row that is over ("its queue row is merged, and a row that is over waits for no merge:
accept it to merge it") until the root accepted it by hand.

The row's first merge was reviewed, as a row whose brief asks for a review is, so its redo's review
launches only because `jbus.prereview.since` reads the brief from the Result that names the merge
taken back on. A redo whose own merge is reverted opens the row again the same way.

Like `test_jbus_prereview.py`, the tests run the real pass against the kitchen's fakes, with a real
origin, over a row jbus launched, and read the reason jmerge gives a pull request from the queue
the pass wrote (`jmerge.rows.short`). The row keeps the merge the revert took back in its
`reverted` column (`jbus.queue.reland`), and every later pass reads that merge out of the world
(`jbus.watch.unlanded`), so the redo's merge is the row's. The last replays the row's
`transitions.jsonl` over RowLife's graph (`features/jbus/spec/RowLife.tla`)."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import queue
from jmerge import ready
from jmerge import reverts as kept
from jmerge import rows as merge_rows
from test_jbus_kitchen import NOW
from test_jbus_prereview import crew_tree, proof, pushed_branch, reviewers, section
from test_jbus_queue import add, rows
from test_rowlife_replay import replay

MERGE = "a" * 40
"""The merge commit of alpha's first pull request, #7, the red tip its revert reverts."""
REVERT = "b" * 40
REDO = "f" * 40
"""The merge commit of the redo, #10, the red tip the second revert, #12, reverts."""
SECOND_REVERT = "9" * 40
SECOND_REDO = "8" * 40


def url(number):
    return f"https://example.test/pull/{number}"


def status(kitchen):
    return rows(kitchen)["alpha"]["status"]


def merged_row(kitchen):
    """alpha, launched, whose crew was reviewed before its pull request, as a row whose brief
    asks for a review is, then wrote its follow-up Result naming #7 and ended its turn, and #7
    merged at `MERGE`. Returns the crew's thread and the brief's path."""
    add(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(minutes=30))
    (thread,) = kitchen.t3.threads
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(
        path.read_text()
        + proof("e" * 40)
        + "Reviewer: mcp:thread-0 #1\n"
        + section("e" * 40)
        + "\n## Result, follow-up (2026-11-13, the pull request)\nStatus: done\n"
        f"Branch: alpha   Pull request: {url(7)}\nLeft: none\n"
    )
    thread.update(status="completed", latestRunId="run-1")
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, MERGE, ago=timedelta(minutes=25))])
    kitchen.poll(NOW - timedelta(minutes=27))
    assert status(kitchen) == "merged"
    return thread, path


def reverted(kitchen, red=MERGE, merge=7, revert=9):
    """The record jbus keeps once it opened the revert of alpha's merge `merge`, at `red`
    (`reverts._own`): `revert` on the branch GitHub names, open. It is the one revert on record:
    `reverts.close` dropped the one before once the row was over again."""
    branch = f"revert-{merge}-alpha"
    record = kept.Revert(red, "alpha", branch, "e" * 40, url(revert))
    jbus.write_json(kitchen.state / kept.NAME, {red: {**kept.record(record), "holders": ["main"]}})
    kitchen.brief(
        branch,
        f"Home: uncategorized\n\n## Result\nStatus: done\n"
        f"Branch: {branch}   Pull request: {url(revert)}\n",
    )
    kitchen.set("open.json", [kitchen.opened(branch, revert)])


def revert_merges(kitchen, merge=7, revert=9, sha=REVERT):
    kitchen.set("open.json", [])
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    landed = kitchen.merged(f"revert-{merge}-alpha", revert, sha, ago=timedelta(minutes=5))
    kitchen.set("merged.json", [*merged, landed])


def told(kitchen, thread, revert=9):
    """The messages jbus sent the crew's thread that name the revert, `revert`."""
    sent = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    return [
        one
        for one in sent
        if one["threadId"] == thread["threadId"] and url(revert) in one["message"]
    ]


def redo_merges(kitchen, thread, path, number, sha, at, commit="the task"):
    """The crew of the reopened row commits its redo and writes its desk proof, jbus launches its
    review, the redo's pull request `number` opens with nothing of jmerge's holding it, and it
    merges at `sha`, the passes running from `at` on. Returns the review jbus launched."""
    tree, head = pushed_branch(kitchen) if commit == "the task" else committed(kitchen, commit)
    thread.update(
        settled=False, archived=False, latestRunId=f"run-{number}", worktreePath=str(tree)
    )
    path.write_text(path.read_text() + proof(head))
    before = len(reviewers(kitchen))
    for minutes in (0, 3):
        kitchen.poll(at + timedelta(minutes=minutes))
    (launched,) = reviewers(kitchen)[before:]
    assert status(kitchen) == "running"

    kitchen.set("open.json", [kitchen.opened("alpha", number)])
    path.write_text(
        path.read_text() + "\n## Result, follow-up (2026-11-13, the redo's pull request)\n"
        f"Status: done\nBranch: alpha   Pull request: {url(number)}\nLeft: none\n"
    )
    kitchen.poll(at + timedelta(minutes=6))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("pr", f"#{number}")
    said = jmerge_says(kitchen)
    assert ready.code_of(said) != ready.ROW_OVER.code, said
    assert said == ""

    kitchen.set("open.json", [])
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    kitchen.set("merged.json", [*merged, kitchen.merged("alpha", number, sha, ago=timedelta(0))])
    kitchen.poll(at + timedelta(minutes=9))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", f"#{number}")
    return launched


def committed(kitchen, text):
    """One more commit of the crew's on alpha's branch, pushed: a redo after a redo."""
    tree = crew_tree(kitchen, "alpha")
    (tree / "docs" / "notes.md").write_text(f"{text}\n")
    kitchen.git("commit", "-q", "-am", f"docs: {text}", cwd=tree)
    kitchen.git("push", "-q", "-f", "origin", "alpha:refs/heads/alpha", cwd=tree)
    head = kitchen.started(
        ["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True
    ).stdout.strip()
    return tree, head


def jmerge_says(kitchen, slug="alpha"):
    """What jmerge's queue rule says of the slug's pull request, read from the queue the pass
    wrote and the brief jbus stores, as `jmerge` reads both."""
    stored = (kitchen.state / "briefs" / f"{slug}.md").read_text()
    return merge_rows.short(list(rows(kitchen).values()), slug, brief=stored)


def redone(kitchen):
    """alpha merged at #7, jbus reverted it in #9, and once #9 merged its redo #10 was reviewed
    and merged. Returns the crew's thread and the brief's path."""
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

    launched = redo_merges(kitchen, thread, path, 10, REDO, NOW)
    assert launched["title"] == "review: alpha, 1"
    return thread, path


def test_a_row_whose_revert_merged_opens_again_and_its_redo_gets_its_review_and_no_row_over_hold(
    kitchen,
):
    """Once #9 merged, the row keeps #7 in its `reverted` column, and `jbus.watch.unlanded` reads
    #7 as no merge of the row's, so the redo #10 goes the way of any row's pull request."""
    redone(kitchen)


def reverted_twice(kitchen):
    """The redo #10 merged, main went red at it, and jbus reverted it too, in #12: once #12
    merges the row is open again, though its `reverted` column already names #7. Returns the
    crew's thread and the brief's path."""
    thread, path = redone(kitchen)
    reverted(kitchen, red=REDO, merge=10, revert=12)
    kitchen.poll(NOW + timedelta(minutes=12))
    assert told(kitchen, thread, revert=12), "jbus tells the crew of the second revert"
    thread.update(status="completed", settled=False, archived=False, latestRunId="run-11")
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#10")
    assert ready.code_of(jmerge_says(kitchen)) == ready.ROW_OVER.code

    revert_merges(kitchen, merge=10, revert=12, sha=SECOND_REVERT)
    kitchen.poll(NOW + timedelta(minutes=15))
    assert status(kitchen) not in ("merged", "done")
    assert rows(kitchen)["alpha"]["pr"] == ""
    assert kitchen.lines("reland") == [
        f"reland alpha: its revert {url(9)} merged, so the row is open for its redo",
        f"reland alpha: its revert {url(12)} merged, so the row is open for its redo",
    ]
    return thread, path


def redone_twice(kitchen):
    """The row reverted twice, whose second redo, #13, is reviewed and merged by the normal path,
    with no row-over hold of jmerge's."""
    thread, path = reverted_twice(kitchen)
    launched = redo_merges(
        kitchen, thread, path, 13, SECOND_REDO, NOW + timedelta(minutes=18), "the second redo"
    )
    assert launched["title"].startswith("review: alpha"), launched["title"]
    for minutes in (30, 33):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#13")
    assert len(kitchen.lines("reland")) == 2


def test_a_row_reverted_twice_opens_again_each_time_and_its_second_redo_is_reviewed_and_merged(
    kitchen,
):
    redone_twice(kitchen)


def test_a_revert_of_a_merge_the_row_already_took_back_opens_nothing(kitchen):
    """alpha's redo #10 is its merge, and its `reverted` column names #7, the merge #9 took back:
    #7 taken back again, by a revert on record that names it late, leaves the row merged at #10,
    while #10's own revert opens it."""
    redone(kitchen)
    assert not queue.reland(kitchen.state, "alpha", url(7), url(9))
    assert (status(kitchen), rows(kitchen)["alpha"]["pr"]) == ("merged", "#10")
    assert queue.reland(kitchen.state, "alpha", url(10), url(12))
    assert status(kitchen) == "left"


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
    redone(kitchen)
    log = kitchen.state / "transitions.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    (moved,) = [line for line in lines if line.get("reverted")]
    assert (moved["from"], moved["to"], moved["reverted"]) == ("merged", "left", url(9))
    code, said = replay(log, capsys)
    assert (code, said) == (0, [f"{len(lines)} lines, {len(lines)} matched, 0 matched no step"])


def test_both_relands_replay_as_steps_of_rowlife(kitchen, capsys):
    """A row merged, reverted, redone, merged and reverted again is a chain of RowLife's steps:
    each reland's line reads as `Reland`, the second from a merge the first did not take back,
    and no pass's line misses."""
    reverted_twice(kitchen)
    log = kitchen.state / "transitions.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    moved = [(line["from"], line["to"], line["reverted"]) for line in lines if line.get("reverted")]
    assert moved == [("merged", "left", url(9)), ("merged", "left", url(12))]
    code, said = replay(log, capsys)
    assert (code, said) == (0, [f"{len(lines)} lines, {len(lines)} matched, 0 matched no step"])
