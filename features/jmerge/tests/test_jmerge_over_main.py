"""A green pull request that shares a file with what main changed since its check started merges
when its head merges cleanly over today's main and the fast guards pass on that merged tree
(`jmerge.cli.Repo.over_main`): GitHub is asked for no update of its branch, and no check runs
again, with main's own run and jbus's revert of a red main's culprit behind it (Josh's vision of
2026-11-06, item F: "merge as soon as green, not stopping to rebase if not needed or to catch up
with main"). One that conflicts waits for its rebase, and one whose guards fail or were stopped
at their limit, a revert jbus opened, and any in a repo that names no guards still go through
the line: GitHub merges main into the branch, and its check at the new head decides.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_fresh.Kitchen`)."""

import json
from dataclasses import replace

import pytest

from jmerge import ready, treeguards
from test_jmerge_cli_merged_tree import MAKEFILE, runs
from test_jmerge_fresh import LINES, Kitchen, asked, git, repo, url
from test_jmerge_in_line import behind
from test_jmerge_order import queue_of
from test_jmerge_revert_line import named

OURS = {"a.txt": "ours\n" + LINES}
"""#7 changes a.txt's first line, and main its last: the two merge cleanly, and overlap."""
THEIRS = {"a.txt": LINES + "main\n"}


@pytest.fixture
def kitchen(tmp_path):
    ran = tmp_path / "guards-ran"
    made = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": MAKEFILE.format(ran=ran)})
    (made.home.state / treeguards.NAME).write_text("make -s guards\n")
    made.ran = ran
    return made


def test_over_main_an_overlapping_one_whose_guards_pass_merges_with_no_update(kitchen):
    kitchen.crew("two", 7, OURS)
    tip = kitchen.on_main(THEIRS)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert f"the guards passed on its tree merged over main at {tip[:12]} in " in said
    assert kitchen.updates() == []
    assert runs(kitchen) == 1
    assert kitchen.at_main("a.txt") == "ours\n" + LINES + "main"


def test_over_main_two_overlapping_ones_both_merge_in_one_run_with_no_update(kitchen):
    """#8 is judged over the tip #7 merged onto: that tip moved, so it is judged again over
    #7's merge, and its guards run on its tree over that."""
    kitchen.crew("two", 7, OURS)
    kitchen.crew("three", 8, {"a.txt": LINES.replace("5\n", "five\n")})
    kitchen.on_main(THEIRS)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second.startswith(f"merged 8 three {kitchen.tip()} ")
    assert kitchen.updates() == []
    assert runs(kitchen) == 2
    assert kitchen.at_main("a.txt") == "ours\n" + LINES.replace("5\n", "five\n") + "main"


def test_over_main_an_overlapping_one_whose_guards_fail_gets_the_branch_update(kitchen):
    """#7 and main each add a `v007_` file: the guards fail on #7's merged tree, so GitHub
    merges main into its branch in the same run, and they do not run again on the next."""
    kitchen.crew("two", 7, {**OURS, "mig/v007_two.txt": "two\n"})
    tip = kitchen.on_main({**THEIRS, "mig/v007_main.txt": "main\n"})
    assert kitchen.run() == [asked(7, tip)]
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []
    assert runs(kitchen) == 1
    kitchen.run()
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []
    assert runs(kitchen) == 1


def test_over_main_an_overlapping_one_whose_guards_were_stopped_gets_the_branch_update(kitchen):
    head = kitchen.crew("two", 7, OURS)
    tip = kitchen.on_main(THEIRS)
    stopped = ready.MERGED_TREE_UNENDED.format(base="main", tip=tip[:12], minutes=10)
    record = {"head": head, "tip": tip, "said": stopped, "note": ""}
    (kitchen.home.state / treeguards.KEPT).write_text(json.dumps({"7": record}))
    assert kitchen.run() == [asked(7, tip)]
    assert kitchen.updates() == ["7"]
    assert runs(kitchen) == 0


def test_over_main_an_overlapping_one_that_conflicts_waits_for_its_rebase(kitchen):
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES[2:]})
    kitchen.on_main({"a.txt": "main\n" + LINES[2:]})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_CONFLICT}"]
    assert kitchen.updates() == []
    assert runs(kitchen) == 0


def test_over_main_an_overlapping_one_in_a_repo_with_no_guards_goes_through_the_line(kitchen):
    (kitchen.home.state / treeguards.NAME).unlink()
    kitchen.crew("two", 7, OURS)
    kitchen.crew("three", 8, {"a.txt": LINES.replace("5\n", "five\n")})
    tip = kitchen.on_main(THEIRS)
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []


def test_over_main_an_overlapping_revert_still_takes_the_line(kitchen):
    """The revert path is as it was: a revert jbus opened is updated and checked, and takes its
    base's line, while one that is no revert merges on its guards beside it."""
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("revert-it", 9, OURS)
    named(queue_of(kitchen.home, []).parent, ("revert-it", url(9)))
    tip = kitchen.on_main({**THEIRS, "b.txt": LINES + "main\n"})
    first, second = kitchen.run()
    assert first == asked(9, tip)
    assert second.startswith("merged 7 two ")
    assert kitchen.updates() == ["9"]
    assert runs(kitchen) == 1


def test_over_main_a_base_that_cannot_be_fetched_waits_saying_so(kitchen, monkeypatch):
    """With no fetch of main, what main changed after the check is not known: the pull request
    waits, judged over no tip, and nothing is merged or asked of GitHub."""
    kitchen.crew("two", 7, OURS)
    kitchen.on_main(THEIRS)
    here = repo(kitchen, monkeypatch)
    git(kitchen.home.main, "remote", "set-url", "origin", str(kitchen.tmp / "gone"))
    why, judged = here.over_main(ready.pull_request(kitchen.pulls["two"]), ())
    assert why == "main could not be fetched to see what changed after its check"
    assert judged == ready.Judged()
    assert kitchen.updates() == []


def test_over_main_a_head_git_cannot_merge_over_the_tip_waits_with_why(kitchen, monkeypatch):
    """A head this checkout does not have is no conflict: it waits with what git said, judged
    over no tip."""
    kitchen.crew("two", 7, OURS)
    kitchen.on_main(THEIRS)
    here = repo(kitchen, monkeypatch)
    one = replace(ready.pull_request(kitchen.pulls["two"]), head="f" * 40)
    why, judged = here.over_main(one, ())
    assert why.startswith("its head could not be merged over today's base (")
    assert why != ready.FRESH_CONFLICT
    assert judged == ready.Judged()
