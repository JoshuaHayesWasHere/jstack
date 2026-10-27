"""Once a stacked link's base merged, jbus moves the link's own commits onto the branch the base
merged into itself, in the pass that sees the merge, and sends its crew nothing: no Claude turn
stands between a merged base and its link.

The tests run the real pass against the kitchen's fakes of T3 Code and GitHub, over a real git
origin: `one` (#10) was squashed into main, and `two` (#11) is one commit on `one`'s branch.
A move that cannot be made mechanically (a conflict, a push the lease refuses, a crew worktree
with work in it) leaves the branch as it was and tells the crew to move it, as before."""

import subprocess
from datetime import timedelta

import pytest

import jsettings
from jmerge import ready
from jmerge import stacked as stacks
from jmerge.cli import Repo
from repo_template import IDENTITY
from test_jbus_github import sends
from test_jbus_kitchen import NOW
from test_jbus_stack import edits, head_line, stacked

__all__ = ["stacked"]


def git(cwd, *args):
    return subprocess.run(
        ["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(tree, name, text, message=""):
    (tree / name).write_text(text)
    git(tree, "add", name)
    git(tree, "commit", "-q", "-m", message or name)
    return git(tree, "rev-parse", "HEAD")


class Stack:
    """The git history of the stack, and what GitHub lists of it."""

    def __init__(self, kitchen, conflict=False):
        self.kitchen, tree = kitchen, kitchen.checkout
        self.start = git(tree, "rev-parse", "main")
        git(tree, "switch", "-q", "-c", "one")
        self.last = commit(tree, "one.txt", "one\n")
        git(tree, "switch", "-q", "-c", "two")
        self.head = commit(tree, "two.txt", "two\n")
        git(tree, "push", "-q", "origin", "one", "two")
        git(tree, "switch", "-q", "main")
        self.merge = commit(tree, "one.txt", "one\n", "one (#10)")
        if conflict:
            commit(tree, "two.txt", "main's own two\n")
        git(tree, "push", "-q", "origin", "main")
        git(tree, "branch", "-q", "-D", "one", "two")
        two = {**kitchen.opened("two", 11), "headRefOid": self.head, "baseRefName": "one"}
        kitchen.set("open.json", [two])
        one = {**kitchen.merged("one", 10, self.merge), "headRefOid": self.last}
        kitchen.set("merged.json", [{**one, "baseRefName": "main"}])

    def origin(self, ref):
        return git(self.kitchen.origin, "rev-parse", ref)


def signed(monkeypatch):
    """jbus's rebase commits as whoever the machine's git names."""
    for who in ("COMMITTER", "AUTHOR"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.com")


@pytest.fixture
def stack(stacked, monkeypatch):
    signed(monkeypatch)
    return Stack(stacked)


@pytest.fixture
def stack_conflict(stacked, monkeypatch):
    """The same, with a commit on main after the merge that writes `two.txt` too."""
    signed(monkeypatch)
    return Stack(stacked, conflict=True)


def unmoved(kitchen, head):
    """What jmerge says of #11 at `head` on main, by its brief's `Stacked on:` line: nothing once
    it may merge."""
    repo = Repo(kitchen.checkout, kitchen.root / "jmerge", None, False, user=jsettings.Settings())
    url = "https://example.test/pull/11"
    pull = ready.PullRequest(
        11, url, "feat: two", "two", head, "main", "MERGEABLE", (), (), False, 1
    )
    text = (kitchen.home / "tasks" / "two.md").read_text()
    return repo.on_stack(pull, "main", stacks.of(text))


def test_a_merged_base_moves_its_link_onto_main_in_the_same_pass_with_no_send(stack):
    kitchen = stack.kitchen
    assert unmoved(kitchen, stack.head)
    kitchen.poll(NOW)
    moved = stack.origin("two")
    assert edits(kitchen) == ["pr edit 11 --base main"]
    assert git(kitchen.origin, "rev-parse", f"{moved}^") == stack.merge
    assert git(kitchen.origin, "show", f"{moved}:two.txt") == "two"
    assert head_line(kitchen) == stacks.Stacked("one", "main", stack.merge)
    assert unmoved(kitchen, moved) == ""
    assert sends(kitchen) == []
    kitchen.poll(NOW + timedelta(minutes=3))
    assert sends(kitchen) == [] and stack.origin("two") == moved


def test_the_crews_own_worktree_follows_the_move(stack):
    kitchen = stack.kitchen
    tree = kitchen.root / "two-tree"
    git(kitchen.checkout, "worktree", "add", "-q", str(tree), stack.head, "-b", "two")
    kitchen.poll(NOW)
    assert git(tree, "rev-parse", "HEAD") == stack.origin("two") != stack.head
    assert git(tree, "status", "--porcelain") == ""
    assert sends(kitchen) == []


def test_a_crew_worktree_with_work_in_it_gets_the_moved_send(stack):
    kitchen = stack.kitchen
    tree = kitchen.root / "two-tree"
    git(kitchen.checkout, "worktree", "add", "-q", str(tree), stack.head, "-b", "two")
    (tree / "two.txt").write_text("half done\n")
    kitchen.poll(NOW)
    assert stack.origin("two") == stack.head
    (said,) = [given["message"] for given in sends(kitchen)]
    assert "one merged as" in said and '"A link that moved"' in said


def test_a_link_that_conflicts_with_main_gets_the_moved_send_and_its_branch_stays(stack_conflict):
    kitchen = stack_conflict.kitchen
    kitchen.poll(NOW)
    assert stack_conflict.origin("two") == stack_conflict.head
    (said,) = [given["message"] for given in sends(kitchen)]
    assert f"one merged as {stack_conflict.merge[:12]}" in said
    assert f"with {stack_conflict.last} as the branch it sat on" in said
    assert head_line(kitchen) == stacks.Stacked("one", "main", stack_conflict.merge)
    assert not list((kitchen.checkout / ".git" / "worktrees").glob("*"))


def test_a_push_the_lease_refuses_gets_the_moved_send(stack):
    """The crew pushed after the pass read the head: the lease names the head read, so the push
    is refused and the crew's commit stays."""
    kitchen = stack.kitchen
    tree = kitchen.root / "elsewhere"
    git(kitchen.checkout, "worktree", "add", "-q", "--detach", str(tree), stack.head)
    pushed = commit(tree, "more.txt", "more\n")
    git(tree, "push", "-q", "origin", f"{pushed}:refs/heads/two")
    git(kitchen.checkout, "worktree", "remove", "--force", str(tree))
    kitchen.poll(NOW)
    assert stack.origin("two") == pushed
    assert len(sends(kitchen)) == 1


def test_a_link_jbus_moved_whose_line_was_not_written_is_not_moved_or_told_again(stack):
    """The push went and the pass ended before the brief's line was written: the next pass
    finds the head already on main, writes the line, and tells the crew nothing."""
    kitchen = stack.kitchen
    import jbus.stack

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(jbus.stack, "_rewrite", lambda *given: None)
        kitchen.poll(NOW)
    moved = stack.origin("two")
    assert moved != stack.head and head_line(kitchen) == stacks.Stacked("one", "one")
    two = {**kitchen.opened("two", 11), "headRefOid": moved, "baseRefName": "main"}
    kitchen.set("open.json", [two])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert stack.origin("two") == moved
    assert head_line(kitchen) == stacks.Stacked("one", "main", stack.merge)
    assert sends(kitchen) == []


def test_a_crew_at_work_is_moved_by_jbus_once_its_turn_ended(stack):
    kitchen = stack.kitchen
    for thread in kitchen.t3.threads:
        thread["status"] = "running"
    kitchen.poll(NOW)
    assert stack.origin("two") == stack.head and sends(kitchen) == []
    assert head_line(kitchen) == stacks.Stacked("one", "one")
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))
    assert git(kitchen.origin, "rev-parse", "two^") == stack.merge
    assert sends(kitchen) == []


def test_a_link_whose_reviewer_is_still_out_gets_the_moved_send(stack):
    kitchen = stack.kitchen
    path = kitchen.home / "tasks" / "two.md"
    path.write_text(path.read_text() + "\n## Result\nReviewer: mcp:a-reviewer #1\n")
    kitchen.poll(NOW)
    assert stack.origin("two") == stack.head
    (said,) = [given["message"] for given in sends(kitchen)]
    assert "one merged as" in said and '"A link that moved"' in said


def test_a_crew_worktree_that_cannot_follow_the_move_is_said(stack):
    """The push went, so the link moved: the line is written, and the pass says the crew's
    worktree stayed behind."""
    kitchen = stack.kitchen
    tree = kitchen.root / "two-tree"
    git(kitchen.checkout, "worktree", "add", "-q", str(tree), stack.head, "-b", "two")
    gitdir = git(tree, "rev-parse", "--absolute-git-dir")
    (kitchen.root / gitdir / "index.lock").write_text("")
    said = kitchen.poll(NOW)
    moved = stack.origin("two")
    assert moved != stack.head and git(tree, "rev-parse", "HEAD") == stack.head
    assert any(f"could not follow the move to {moved[:12]}" in line for line in said)
    assert head_line(kitchen) == stacks.Stacked("one", "main", stack.merge)
    assert sends(kitchen) == []
