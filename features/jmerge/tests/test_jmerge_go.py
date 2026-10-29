"""`jmerge` merges a pull request only while its row's go holds for the brief as jbus stores it,
the same answer jbus's launch gives (`jbus.queue.has_go`). An `add` that changes a brief keeps
the row's `approved` set, so the flag alone is no go (simplify-4's story 3, NoMergeWithoutGo).

The tests run the command against a real origin and a fake `gh`, with the kitchen of
`test_jmerge_accept_act`.
"""

import json

import test_jmerge_accept_act as accept_act
from jbus import queue

STORED = '# delta: the goal\nTask: "ours"\n'

kitchen = accept_act.kitchen


def queued(kitchen, approved, brief_sha, stored):
    """The row of `delta`, whose pull request #9 is open, and its brief as jbus stores it."""
    kitchen.crew("delta", 9, {"a.txt": "ours\n"})
    row = {
        "slug": "delta",
        "priority": 0,
        "depends": [],
        "approved": approved,
        "brief_sha": brief_sha,
        "status": "pr",
        "thread": "",
        "pr": "#9",
        "checks": "",
        "updated": "",
        "why": "",
        "since": "",
    }
    (kitchen.jbus / "queue.json").write_text(json.dumps([row]))
    (kitchen.jbus / "briefs").mkdir(exist_ok=True)
    (kitchen.jbus / "briefs" / "delta.md").write_text(stored)
    return row


def test_a_row_whose_go_no_longer_holds_for_its_brief_waits_on_the_user(kitchen):
    other = '# delta: another goal\nTask: "other"\n'
    row = queued(kitchen, "yes, typed", queue.brief_sha(STORED), other)
    assert row["approved"] and not queue.approved_text(row, other)
    (said,) = kitchen.run()
    assert said.startswith("wait 9 ") and "has no go" in said, said
    assert not kitchen.calls(), "something merged"


def test_a_row_whose_go_holds_for_its_brief_merges(kitchen):
    row = queued(kitchen, "yes, typed", queue.brief_sha(STORED), STORED)
    assert queue.approved_text(row, STORED)
    (said,) = kitchen.run()
    assert said.startswith("merged 9 "), said


def test_a_row_with_a_go_and_no_stored_brief_waits(kitchen):
    queued(kitchen, "yes, typed", queue.brief_sha(STORED), STORED)
    (kitchen.jbus / "briefs" / "delta.md").unlink()
    (said,) = kitchen.run()
    assert said.startswith("wait 9 ") and "has no go" in said, said


def test_a_row_with_no_go_waits(kitchen):
    queued(kitchen, "", "", STORED)
    (said,) = kitchen.run()
    assert said.startswith("wait 9 ") and "has no go" in said, said
