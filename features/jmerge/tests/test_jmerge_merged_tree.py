"""Before `jmerge` merges a pull request on its existing check, it merges the head over today's
base with `git merge-tree`, pushes nothing, and runs the repo's fast guards, the command its
state's `merged-tree-guards` file names, on that tree. A clash two pull requests make together,
each green alone, shows there: the pull request waits with a line that names the failing guard
and what its crew does, and the guards' run time is in the line of a merge.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_fresh.Kitchen`).
The guard is a make target that fails when two files of `mig/` share a number, as two `v007_`
migrations did on 2026-11-03."""

import json
import time
from types import SimpleNamespace

import pytest

from jmerge import ready, treeguards
from test_jmerge_fresh import AFTER, LINES, STARTED, Kitchen, git, url

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


def test_merged_tree_guard_named_from_the_output():
    pytest_said = "....\nFAILED features/x/tests/test_y.py::test_z - assert 0\n1 failed\n"
    make_said = "Found 1 error.\nmake[1]: *** [Makefile:53: lint] Error 1\nmake: *** [x] Error 2\n"
    assert treeguards.guard(pytest_said + make_said) == "features/x/tests/test_y.py::test_z"
    assert treeguards.guard(make_said) == "lint"
    assert treeguards.guard("one\nthe last line\n\n") == "the last line"
    assert treeguards.guard("") == treeguards.UNNAMED


def test_merged_tree_guards_that_run_past_their_time_are_stopped_with_their_children(tmp_path):
    marker = tmp_path / "child"
    command = f"sh -c 'sleep 3; touch {marker}' & sleep 30"
    ran = treeguards.run_guards(command, tmp_path, {}, timeout=1)
    assert ran.code is None and ran.seconds < 10
    time.sleep(3)
    assert not marker.exists(), "the guards' child outlived the stop"


class Tree:
    """A main checkout whose origin's main moved past a pull request's head: `tip` is main's,
    and `head` the pull request's, which does not hold it."""

    def __init__(self, tmp_path, ours="b\n", theirs="c\n", path="b.txt"):
        self.origin = tmp_path / "origin.git"
        self.main = tmp_path / "main"
        self.state = tmp_path / "state"
        self.state.mkdir()
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.main))
        self.commit({"a.txt": "a\n"})
        git(self.main, "push", "-q", "origin", "HEAD:main")
        base = git(self.main, "rev-parse", "HEAD")
        self.head = self.commit({path: ours})
        git(self.main, "checkout", "-q", base)
        self.tip = self.commit({"c.txt" if path == "b.txt" else path: theirs})
        git(self.main, "push", "-q", "origin", "HEAD:main")
        self.one = SimpleNamespace(number=7, head=self.head, base="main")

    def commit(self, files):
        for path, text in files.items():
            (self.main / path).write_text(text)
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "x")
        return git(self.main, "rev-parse", "HEAD")

    def guards(self, command):
        (self.state / treeguards.NAME).write_text(command + "\n")
        return treeguards.Guards(self.main, self.state, True)


def values(tree):
    return {"base": "main", "tip": tree.tip[:12]}


def test_merged_tree_guards_that_passed_are_not_run_again(tmp_path):
    tree = Tree(tmp_path)
    guards = tree.guards('test -e b.txt && test -e c.txt && test "$BASE" = ' + tree.tip)
    said, note = guards.of(tree.one, tree.tip)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])
    guards.command = "false"
    assert guards.of(tree.one, tree.tip) == ("", note)
    assert not (tree.state / treeguards.TREE).exists()


def test_merged_tree_guards_start_no_more_once_a_run_spent_its_time(tmp_path):
    tree = Tree(tmp_path)
    guards = tree.guards("true")
    guards.spent = treeguards.RUN_SECONDS
    assert guards.of(tree.one, tree.tip) == (ready.MERGED_TREE_NO_TIME.format(**values(tree)), "")


def test_merged_tree_of_a_head_that_conflicts_with_the_tip_waits_for_a_rebase(tmp_path):
    tree = Tree(tmp_path, ours="ours\n", theirs="theirs\n", path="a.txt")
    assert tree.guards("true").of(tree.one, tree.tip) == (ready.FRESH_CONFLICT, "")


def test_merged_tree_that_cannot_be_built_says_why(tmp_path):
    tree = Tree(tmp_path)
    said, _ = tree.guards("true").of(tree.one, "f" * 40)
    assert said.startswith(ready.MERGED_TREE_UNBUILT.format(base="main", tip="f" * 12, why="")[:-2])
    (tree.state / treeguards.TREE).write_text("in the way\n")
    said, _ = tree.guards("true").of(tree.one, tree.tip)
    assert said.startswith(ready.MERGED_TREE_UNBUILT.format(**values(tree), why="")[:-2])
    assert said.endswith("already exists)")


def test_merged_tree_guards_past_their_limit_wait_and_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 1)
    tree = Tree(tmp_path)
    guards = tree.guards("sleep 20")
    unended = ready.MERGED_TREE_UNENDED.format(**values(tree), minutes=0)
    assert guards.of(tree.one, tree.tip) == (unended, "")
    assert treeguards.Guards(tree.main, tree.state, True).kept(tree.one, tree.tip) == unended


def test_merged_tree_that_passed_while_main_moved_waits_for_the_next_run(tmp_path):
    tree = Tree(tmp_path)
    later = tree.commit({"d.txt": "d\n"})
    guards = tree.guards(f"git -C {tree.main} push -q origin {later}:refs/heads/main")
    assert guards.of(tree.one, tree.tip) == (ready.MAIN_MOVED.format(base="main"), "")


def test_merged_tree_records_of_pull_requests_no_longer_open_are_dropped(tmp_path):
    tree = Tree(tmp_path)
    guards = tree.guards("false")
    held, _ = guards.of(tree.one, tree.tip)
    assert held and guards.kept(tree.one, tree.tip) == held
    guards.open_only({"8": "x"})
    assert json.loads((tree.state / treeguards.KEPT).read_text()) == {}
    assert treeguards.Guards(tree.main, tree.state, True).kept(tree.one, tree.tip) == ""
