"""Branches on a kitchen's origin, and the branch a crew's worktree started on, for the tests of
launches that jbus makes the worktree of (`jbus.crewtree`)."""

import subprocess

from repo_template import IDENTITY


def git_said(kitchen, *args):
    ran = subprocess.run(
        ["git", *IDENTITY, *args], cwd=kitchen.checkout, check=True, capture_output=True, text=True
    )
    return ran.stdout.strip()


def pushed(kitchen, *branches):
    """Put each branch on origin, at a commit of its own on main whose subject is its name, as a
    pull request's head or a release branch is there before a crew launches on it. A branch origin
    has already stays as it is."""
    for branch in branches:
        there = subprocess.run(
            [
                "git",
                "-C",
                str(kitchen.origin),
                "rev-parse",
                "-q",
                "--verify",
                f"refs/heads/{branch}",
            ],
            capture_output=True,
        )
        if there.returncode == 0:
            continue
        made = git_said(kitchen, "commit-tree", "main^{tree}", "-p", "main", "-m", branch)
        git_said(kitchen, "push", "-q", "origin", f"{made}:refs/heads/{branch}")


def started_on(kitchen, slug):
    """Return the branch that the crew branch `slug`, which jbus made, starts on: the subject of its
    tip, a commit `pushed` made, or `start` for main."""
    return git_said(kitchen, "log", "-1", "--format=%s", f"refs/heads/{slug}")
