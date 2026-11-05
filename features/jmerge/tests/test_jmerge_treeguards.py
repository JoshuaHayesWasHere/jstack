"""`jmerge.treeguards` on a real origin and checkout: how the fast guards on a pull request's
tree merged over today's base pass, fail, wait and are kept, and how a failed guard is named.
`test_jmerge_cli_merged_tree.py` drives the same through the `jmerge` command."""

import json
import os
import re
import shutil
import time
from types import SimpleNamespace

from jmerge import ready, treeguards
from test_jmerge_fresh import git
from testing.paths import REPO


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


SCOUT = "features/verify-jstack/tests/test_verify_jstack.py::" + (
    "test_a_scout_goes_from_its_request_to_a_launched_thread_with_no_branch"
)


def jbus_environment():
    """The environment jbus's merge unit gives `jmerge`, and with it the guards: systemd's few
    variables and the unit's PATH, with this run's uv on it, as a machine with jbus has its
    own in ~/.local/bin."""
    unit = (REPO / "features" / "jbus" / "units" / "jbus-merge.service").read_text()
    path = re.search(r"^Environment=PATH=(.*)$", unit, re.MULTILINE)[1]
    path = path.replace("%h", os.environ["HOME"])
    uv = os.path.dirname(shutil.which("uv"))
    names = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR")
    return {name: os.environ[name] for name in names if name in os.environ} | {
        "PATH": path if uv in path.split(":") else f"{uv}:{path}"
    }


def test_merged_tree_guards_drive_the_sandbox_on_the_path_jbus_gives_them(monkeypatch):
    """The guards run where jbus runs `jmerge`, on its unit's short PATH, and still find what a
    desk's shell finds: on Arch the drive's `shasum` is in /usr/bin/core_perl, off that PATH,
    and a guard that missed it held every pull request with this test."""
    monkeypatch.setattr(os, "environ", jbus_environment())
    command = f"uv run pytest -q -p no:cacheprovider {SCOUT}"
    ran = treeguards.run_guards(command, REPO, {"BASE": "HEAD"}, treeguards.LIMIT_SECONDS)
    assert ran.code == 0, ran.said
    assert treeguards.guard(ran.said).startswith("1 passed")


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


def test_merged_tree_guards_past_their_limit_wait_once_and_run_again_next_run(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 1)
    tree = Tree(tmp_path)
    guards = tree.guards("sleep 20")
    unended = ready.MERGED_TREE_UNENDED.format(**values(tree), minutes=0)
    assert guards.of(tree.one, tree.tip) == (unended, "")
    assert guards.kept(tree.one, tree.tip) == ""
    assert not (tree.state / treeguards.KEPT).exists()
    again = treeguards.Guards(tree.main, tree.state, True)
    assert again.kept(tree.one, tree.tip) == ""
    again.command = "true"
    said, note = again.of(tree.one, tree.tip)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])


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
