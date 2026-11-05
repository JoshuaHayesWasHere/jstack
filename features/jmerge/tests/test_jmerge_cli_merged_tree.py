"""Before `jmerge` merges a pull request on its existing check, it merges the head over today's
base with `git merge-tree`, pushes nothing, and runs the repo's fast guards, the command its
state's `merged-tree-guards` file names, on that tree. A clash two pull requests make together,
each green alone, shows there: the pull request waits with a line that names the failing guard
and what its crew does, and the guards' run time is in the line of a merge.

The tests run the `jmerge` command, `jmerge.cli`, against a real origin and a fake `gh`
(`test_jmerge_fresh.Kitchen`). `test_jmerge_treeguards.py` drives `jmerge.treeguards` itself.
The guard is a make target that fails when two files of `mig/` share a number, as two `v007_`
migrations did on 2026-11-03."""

import json

import pytest

from jmerge import ready, treeguards
from test_jmerge_fresh import AFTER, LINES, STARTED, Kitchen, url

MAKEFILE = """\
guards: numbers

numbers:
\t@echo ran >> {ran}
\t@test -z "$$(ls mig 2> /dev/null | sed 's/_.*//' | sort | uniq -d)"
"""


@pytest.fixture
def kitchen(tmp_path):
    ran = tmp_path / "guards-ran"
    made = Kitchen(tmp_path, {"a.txt": LINES, "Makefile": MAKEFILE.format(ran=ran)})
    (made.home.state / treeguards.NAME).write_text("make -s guards\n")
    made.ran = ran
    return made


def runs(kitchen):
    """How many times the guards ran."""
    return len(kitchen.ran.read_text().split()) if kitchen.ran.exists() else 0


def relisted(kitchen):
    """GitHub once the merges are made: a merged pull request is no longer listed."""
    stub = kitchen.home.stub
    listed = [p for p in kitchen.pulls.values() if not (stub / f"merged-{p['number']}").exists()]
    (stub / "list.json").write_text(json.dumps(listed))


def fails(number, tip, guard="numbers"):
    return f"wait {number} {url(number)}: " + ready.MERGED_TREE_FAILS.format(
        base="main", tip=tip[:12], guard=guard
    )


def test_merged_tree_of_two_green_pull_requests_that_fail_a_guard_together_holds_the_second(
    kitchen,
):
    """#6 and #7 each add a `v007_` file, and each passes the guard alone. #7's check started
    after #6 merged, so it merges on that check, and only its tree merged over main shows the
    clash."""
    kitchen.crew("one", 6, {"mig/v007_one.txt": "one\n"})
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"}, checks=(AFTER,))
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second == fails(7, kitchen.tip())
    assert len(kitchen.calls()) == 1
    assert kitchen.updates() == []
    logged = (kitchen.home.state / "merge.log").read_text()
    assert f"{second} [merged-tree-fails]" in logged


def test_merged_tree_that_failed_is_not_run_again_for_the_same_head_and_tip(kitchen):
    kitchen.crew("one", 6, {"mig/v007_one.txt": "one\n"})
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"}, checks=(AFTER,))
    kitchen.run()
    relisted(kitchen)
    ran = runs(kitchen)
    tip = kitchen.tip()
    assert kitchen.run() == [fails(7, tip)]
    assert kitchen.run("--check") == [fails(7, tip)]
    assert runs(kitchen) == ran
    assert len(kitchen.calls()) == 1


def test_merged_tree_that_passes_merges_as_before_with_the_guards_time_in_the_merge_log(kitchen):
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"}, checks=(AFTER,))
    tip = kitchen.on_main({"mig/v008_main.txt": "main\n"})
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    took = said.split(", ")[1]
    assert took.startswith(f"the guards passed on its tree merged over main at {tip[:12]} in ")
    assert took.endswith(" s")
    assert runs(kitchen) == 1
    assert took in (kitchen.home.state / "merge.log").read_text()
    assert kitchen.at_main("mig/v008_main.txt") == "main"


def test_merged_tree_is_not_built_when_the_head_holds_the_tip(kitchen):
    """A head that already holds main's tip is the tree its check ran on: the guards would run
    again on what CI ran them on."""
    kitchen.crew("one", 6, {"mig/v007_one.txt": "one\n"})
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ")
    assert runs(kitchen) == 0


def test_merged_tree_with_no_guards_file_merges_as_before(kitchen):
    (kitchen.home.state / treeguards.NAME).unlink()
    kitchen.crew("one", 6, {"mig/v007_one.txt": "one\n"})
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"}, checks=(AFTER,))
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ") and second.startswith("merged 7 two ")
    assert runs(kitchen) == 0


def test_merged_tree_held_pull_request_holds_up_no_other(kitchen):
    """#7, held for its crew, keeps no place that #8 behind it waits for: #8, whose check main
    moved past, has GitHub merge main into its branch in the same run."""
    kitchen.crew("one", 6, {"mig/v007_one.txt": "one\n"})
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"}, checks=(AFTER,))
    kitchen.crew("three", 8, {"a.txt": "three\n" + LINES}, checks=(STARTED,))
    first, second, third = kitchen.run()
    tip = kitchen.tip()
    assert first.startswith("merged 6 one ") and second == fails(7, tip)
    assert third == f"wait 8 {url(8)}: " + ready.BASE_MOVED_ASKED.format(base="main", tip=tip[:12])
    assert kitchen.updates() == ["8"]
