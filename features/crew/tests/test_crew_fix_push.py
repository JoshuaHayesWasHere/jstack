"""The crew skill's push of a fix: a new commit on the head GitHub has, never a rewrite."""

import os
import subprocess

from crew_helpers import PullRequest, block, git

ABOUT = "a rebase is not pushed yet"


def pushes(pr):
    """What the block prints in the crewmate's worktree."""
    return subprocess.run(
        ["sh", "-c", block("The review", ABOUT)],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env=os.environ,
    ).stdout


def origin(pr):
    return git(pr.work, "ls-remote", "origin", "a-task").split()[0]


def test_a_new_commit_on_the_pushed_head_is_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"
    assert origin(pr) == pr.head()


def test_an_amended_head_is_not_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "commit", "-q", "--amend", "-m", "the task, amended")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {was}\n"
    assert origin(pr) == was


def test_a_rebase_nothing_asked_for_is_not_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {was}\n"
    assert origin(pr) == was


def test_a_rebase_for_a_conflict_is_left_to_its_own_block(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    (pr.git_dir / "crew-before-rebase").write_text(f"{was} main {was}\n")
    assert (
        pushes(pr) == "no push: a rebase is not pushed yet, push it with the block of A conflict\n"
    )
    assert origin(pr) == was


def test_a_record_left_by_a_rebase_pushed_some_other_way_stops_no_fix(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    git(
        pr.work,
        "push",
        "-q",
        f"--force-with-lease=refs/heads/a-task:{was}",
        "origin",
        "HEAD:a-task",
    )
    (pr.git_dir / "crew-before-rebase").write_text(f"{was} main {was}\n")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"


def test_a_head_behind_a_merge_github_made_is_not_pushed_and_merges_it_in(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    other = tmp_path / "other"
    git(other, "fetch", "-q", "origin")
    git(other, "checkout", "-q", "-b", "a-task", "origin/a-task")
    git(other, "merge", "-q", "--no-edit", "origin/main")
    git(other, "push", "-q", "origin", "HEAD:a-task")
    merged = git(other, "rev-parse", "HEAD")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {merged}\n"
    git(pr.work, "merge", "-q", "--no-edit", "FETCH_HEAD")
    assert pushes(pr) == f"pushed {pr.head()}\n"


def test_the_way_back_from_an_amend_keeps_the_fix_and_needs_no_force(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    (pr.work / "fix.txt").write_text("the fix\n")
    git(pr.work, "add", "fix.txt")
    git(pr.work, "commit", "-q", "--amend", "-m", "the task, amended")
    pushes(pr)
    git(pr.work, "reset", "-q", "--soft", "FETCH_HEAD")
    git(pr.work, "commit", "-q", "-m", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"
    assert git(pr.work, "show", f"{origin(pr)}:fix.txt") == "the fix"
