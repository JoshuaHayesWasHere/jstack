"""A green pull request that shares a file with what main changed since its check started merges
on that existing check when its head merges cleanly over today's main
(`jmerge.cli.Repo.over_main`): GitHub is asked for no update of its branch, no check runs again,
and nothing runs on its merged tree, with main's own run and jbus's revert of a red main's
culprit behind it (Josh's vision of 2026-11-06, item F: "merge as soon as green, not stopping to
rebase if not needed or to catch up with main"). One that conflicts waits for its rebase, and a
revert jbus opened still goes through the line: GitHub merges main into the branch, and its
check at the new head decides.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_fresh.Kitchen`)."""

from dataclasses import replace

import pytest

from jmerge import ready
from test_jmerge_fresh import LINES, Kitchen, asked, git, repo, url
from test_jmerge_order import queue_of
from test_jmerge_revert_line import named

OURS = {"a.txt": "ours\n" + LINES}
"""#7 changes a.txt's first line, and main its last: the two merge cleanly, and overlap."""
THEIRS = {"a.txt": LINES + "main\n"}


@pytest.fixture
def kitchen(tmp_path):
    return Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES})


def test_over_main_an_overlapping_one_that_merges_cleanly_merges_with_no_update(kitchen):
    kitchen.crew("two", 7, OURS)
    kitchen.on_main(THEIRS)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert kitchen.updates() == []
    assert kitchen.at_main("a.txt") == "ours\n" + LINES + "main"


def test_over_main_two_overlapping_ones_both_merge_in_one_run_with_no_update(kitchen):
    """#8 is judged over the tip #7 merged onto: that tip moved, so it is judged again over
    #7's merge, and merges on its own check over that."""
    kitchen.crew("two", 7, OURS)
    kitchen.crew("three", 8, {"a.txt": LINES.replace("5\n", "five\n")})
    kitchen.on_main(THEIRS)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second.startswith(f"merged 8 three {kitchen.tip()} ")
    assert kitchen.updates() == []
    assert kitchen.at_main("a.txt") == "ours\n" + LINES.replace("5\n", "five\n") + "main"


def test_over_main_an_overlapping_one_that_conflicts_waits_for_its_rebase(kitchen):
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES[2:]})
    kitchen.on_main({"a.txt": "main\n" + LINES[2:]})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_CONFLICT}"]
    assert kitchen.updates() == []


def test_over_main_an_overlapping_revert_still_takes_the_line(kitchen):
    """A revert jbus opened is updated and checked, and takes its base's line, while one that is
    no revert merges on its existing check beside it."""
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("revert-it", 9, OURS)
    named(queue_of(kitchen.home, []).parent, ("revert-it", url(9)))
    tip = kitchen.on_main({**THEIRS, "b.txt": LINES + "main\n"})
    first, second = kitchen.run()
    assert first == asked(9, tip)
    assert second.startswith("merged 7 two ")
    assert kitchen.updates() == ["9"]


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
    """A head with no history in common with main is no conflict: git refuses the merge, and the
    pull request waits with what git said, judged over no tip."""
    kitchen.crew("two", 7, OURS)
    kitchen.on_main(THEIRS)
    here = repo(kitchen, monkeypatch)
    main = kitchen.home.main
    tree = git(main, "rev-parse", "HEAD^{tree}")
    alone = git(main, "commit-tree", tree, "-m", "a history of its own")
    one = replace(ready.pull_request(kitchen.pulls["two"]), head=alone)
    why, judged = here.over_main(one, ())
    assert why == ready.UNMERGED.format(why="fatal: refusing to merge unrelated histories")
    assert judged == ready.Judged()
