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

    def __init__(self, kitchen, conflict=False, fixed=False, rewritten="", into="main"):
        """`one` is pushed before `two` is stacked on it, so the checkout's reflog of
        `origin/one` records the head `two` sits on. Then `one` takes a `fixed` commit, or is
        `rewritten`: its one commit `amended` to new content, or a second commit `reworded` to
        the same content or `changed` to new content."""
        self.kitchen, tree = kitchen, kitchen.checkout
        self.start = git(tree, "rev-parse", "main")
        git(tree, "switch", "-q", "-c", "one")
        self.last = commit(tree, "one.txt", "one\n")
        if rewritten in ("reworded", "changed"):
            self.last = commit(tree, "one-more.txt", "more\n")
        git(tree, "push", "-q", "origin", "one")
        git(tree, "switch", "-q", "-c", "two")
        self.head = commit(tree, "two.txt", "two\n")
        git(tree, "switch", "-q", "one")
        if fixed:
            self.last = commit(tree, "fix.txt", "fix\n")
        if rewritten:
            if rewritten == "amended":
                (tree / "one.txt").write_text("one, rewritten\n")
            if rewritten == "changed":
                (tree / "one-more.txt").write_text("more\nand other lines\n")
            git(tree, "commit", "-q", "-a", "--amend", "-m", f"{rewritten} one")
            self.last = git(tree, "rev-parse", "HEAD")
        git(tree, "push", "-q", "-f", "origin", "one", "two")
        git(tree, "switch", "-q", "main")
        if into != "main":
            git(tree, "switch", "-q", "-c", into)
        self.merge = commit(tree, "one.txt", "one\n", "one (#10)")
        if conflict:
            commit(tree, "two.txt", "main's own two\n")
        git(tree, "push", "-q", "origin", into)
        git(tree, "switch", "-q", "main")
        git(tree, "branch", "-q", "-D", "one", "two")
        two = {**kitchen.opened("two", 11), "headRefOid": self.head, "baseRefName": "one"}
        kitchen.set("open.json", [two])
        one = {**kitchen.merged("one", 10, self.merge), "headRefOid": self.last}
        kitchen.set("merged.json", [{**one, "baseRefName": into}])

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


def unmoved(kitchen, head, base="main", bases=()):
    """What jmerge says of #11 at `head` on `base`, by its brief's `Stacked on:` line and the
    merge bases its project names: nothing once it may merge."""
    repo = Repo(kitchen.checkout, kitchen.root / "jmerge", None, False, user=jsettings.Settings())
    url = "https://example.test/pull/11"
    pull = ready.PullRequest(11, url, "feat: two", "two", head, base, "MERGEABLE", (), (), False, 1)
    stacked = stacks.of((kitchen.home / "tasks" / "two.md").read_text())
    return ready.held(pull, "main", stacked, bases) or repo.on_stack(pull, "main", stacked)


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


def test_a_link_whose_reviewer_is_still_out_is_left_and_moved_once_its_review_is_written(stack):
    """A crew puts a move off while its review is out, so the outbox's `review` rule holds the
    link: jbus neither moves it nor tells its crew. The pass after the review is written moves
    it, with no send."""
    kitchen = stack.kitchen
    path = kitchen.home / "tasks" / "two.md"
    path.write_text(path.read_text() + "\n## Result\nReviewer: mcp:a-reviewer #1\n")
    said = kitchen.poll(NOW)
    assert stack.origin("two") == stack.head and sends(kitchen) == []
    assert any("held by the review rule" in line for line in said)
    path.write_text(
        path.read_text()
        + f"\n## Review\nBy: mcp:a-reviewer #1\nVerdict: clean\nHead: {stack.head}\n"
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    assert stack.origin("two") != stack.head and sends(kitchen) == []


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


def test_a_base_merged_into_a_merge_base_moves_its_link_onto_that_base(stacked, monkeypatch):
    """The sidebar's rows merge into `t3code-jstack`, a merge base of the project: a link on a
    row that merged there is moved onto it, and jmerge then merges it there as it would one on
    main."""
    signed(monkeypatch)
    stack = Stack(stacked, into="t3code-jstack")
    kitchen = stack.kitchen
    stack.kitchen.poll(NOW)
    moved = stack.origin("two")
    assert edits(kitchen) == ["pr edit 11 --base t3code-jstack"]
    assert git(kitchen.origin, "rev-parse", f"{moved}^") == stack.merge
    assert head_line(kitchen) == stacks.Stacked("one", "t3code-jstack", stack.merge)
    assert stack.origin("main") == stack.start
    assert unmoved(kitchen, moved, "t3code-jstack", ("t3code-jstack",)) == ""
    assert sends(kitchen) == []


def test_a_link_whose_base_took_commits_while_open_is_moved_from_the_fork_with_no_send(
    stacked, monkeypatch
):
    """`one` took a review fix after `two` was stacked on it, and `two` was not told of it, so its
    head does not hold `one`'s last head. `one` only grew, so jbus moves `two`'s own commit, the
    one above where it left `one`, onto main in the pass that sees the merge, and sends nothing."""
    signed(monkeypatch)
    stack = Stack(stacked, fixed=True)
    stacked.poll(NOW)
    moved = stack.origin("two")
    assert git(stacked.origin, "rev-parse", f"{moved}^") == stack.merge
    assert git(stacked.origin, "show", f"{moved}:two.txt") == "two"
    assert head_line(stacked) == stacks.Stacked("one", "main", stack.merge)
    assert unmoved(stacked, moved) == ""
    stacked.poll(NOW + timedelta(minutes=3))
    assert sends(stacked) == [] and stack.origin("two") == moved


@pytest.mark.parametrize("rewritten", ["amended", "reworded", "changed"])
def test_a_link_whose_base_was_rewritten_is_left_and_told_once_when_it_merged(
    stacked, monkeypatch, rewritten
):
    """`one` was rewritten after `two` was stacked on it, so `two` holds a commit `one` no longer
    has: its only commit amended, or its top commit reworded or changed to new lines above a
    commit it kept. The reflog of `origin/one` records the head `two` sits on, which `one`'s last
    head does not hold, so jbus leaves the branch as it was and tells the crew once, in the pass
    that sees the merge."""
    signed(monkeypatch)
    stack = Stack(stacked, rewritten=rewritten)
    said = stacked.poll(NOW)
    assert any("jbus left its branch as it was (its head does not hold" in line for line in said)
    assert stack.origin("two") == stack.head
    (told,) = [given["message"] for given in sends(stacked)]
    assert "one merged as" in told and f"with {stack.last} as the branch it sat on" in told
    assert head_line(stacked) == stacks.Stacked("one", "main", stack.merge)
    stacked.poll(NOW + timedelta(minutes=3))
    assert len(sends(stacked)) == 1


def test_a_link_whose_base_left_no_record_is_left_and_told_once(stacked, monkeypatch):
    """`one` only grew, but no reflog of this machine records the head `two` was stacked on, so
    nothing tells a base that grew from one that was rewritten: jbus leaves the branch as it was
    and tells the crew once."""
    signed(monkeypatch)
    stack = Stack(stacked, fixed=True)
    git(stacked.checkout, "update-ref", "-d", "refs/remotes/origin/one")
    said = stacked.poll(NOW)
    assert any("jbus left its branch as it was (its head does not hold" in line for line in said)
    assert stack.origin("two") == stack.head
    assert len(sends(stacked)) == 1
