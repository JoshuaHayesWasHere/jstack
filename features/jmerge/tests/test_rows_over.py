"""jmerge reads whether a row is over from jbus (`jmerge.bus.over`, which jbus answers with
`jbus.work.over`), and holds the pull request of a row that is over.

The tests run the real `jmerge` as `test_jmerge_order.py` runs it: `alpha` (#7) and `beta` (#8)
are open on one reviewed head, and the queue is the project's `queue.json`. The user's accept runs
in the kitchen of `test_jmerge_accept_act`, whose fake T3 Code gives jbus the user's own message."""

import json

import pytest

import test_jmerge_accept_act as accept_act
from jmerge import judgement, ready
from test_home_merge import URL
from test_jmerge_fresh import url
from test_jmerge_order import BETA_URL, merged_numbers, queue_of, row, two

__all__ = ["two"]

kitchen = accept_act.kitchen


@pytest.mark.parametrize("over", ["done", "merged"])
def test_jmerge_holds_the_pull_request_of_a_row_that_is_over(two, over):
    queue_of(two.home, [row("alpha", status=over, pr="#7"), row("beta", pr="#8")])
    said = two.run()
    assert said[0] == f"hold 7 {URL}: {ready.ROW_OVER.format(status=over)}"
    assert merged_numbers(said) == [8]


def test_a_merge_after_child_waits_until_its_parent_is_over(two):
    path = queue_of(
        two.home,
        [row("alpha", status="running"), row("beta", pr="#8", merge_after=["alpha"])],
    )
    said = two.run("--check")
    assert said[1] == f"wait 8 {BETA_URL}: merges after alpha (no pull request yet), not merged yet"
    table = path.read_text().replace('"running"', '"done"')
    path.write_text(table)
    assert two.run("--check")[1].startswith("ready 8 ")


@pytest.mark.parametrize("over", ["done", "merged"])
def test_the_users_accept_merges_the_pull_request_of_a_row_that_is_over_at_its_head(kitchen, over):
    """`ROW_OVER` says to accept it to merge it, and the accept merges it: the re-judge of the
    accept lifts it at the head it was given at, as it lifts each hold of its kind."""
    stored = "# delta: the goal\n"
    over_row = {**row("delta", status=over, pr="#9"), "brief_sha": judgement.brief_sha(stored)}
    (kitchen.jbus / "briefs").mkdir()
    (kitchen.jbus / "briefs" / "delta.md").write_text(stored)
    (kitchen.jbus / "queue.json").write_text(json.dumps([over_row]))
    head = accept_act.held(kitchen, "delta", 9, {"a.txt": "ours\n" + accept_act.LINES})
    assert kitchen.run() == [f"hold 9 {url(9)}: {ready.ROW_OVER.format(status=over)}"]
    ref = accept_act.said(kitchen, "merge 9")
    out = accept_act.jmerge(kitchen, "--accept", "9", "--as", "user", "--message", ref)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 9 {url(9)}: {ready.ROW_OVER.format(status=over)}, ")
    assert f"lifted at {head[:12]} " in out[0]
    assert out[-1].startswith("merged 9 delta "), out
    assert [call.split()[2] for call in kitchen.calls()] == ["9"]
