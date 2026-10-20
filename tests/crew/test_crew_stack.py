"""The crew skill's base for a pull request and "A link that moved"."""

import os
import subprocess

import pytest

import test_home_merge as merge
from crew.helpers import BRIEF, Link, PullRequest, block, covers, git, with_field
from jmerge import ready


def base_of(tmp_path, brief, knows_default=True):
    """What the block that prints a pull request's base says for a brief, in a clone of a
    repo whose default branch is `main`."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    PullRequest.commit(work, "a.txt", "one\n", "start")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    if knows_default:
        git(work, "remote", "set-head", "origin", "main")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    ran = subprocess.run(
        ["sh", "-c", block("Do the task", "Stack:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=work,
        env={**os.environ, "H": str(tmp_path)},
        check=True,
    )
    (line,) = ran.stdout.splitlines()
    return line


def test_a_brief_with_no_stack_line_opens_its_pull_request_on_the_default_branch(tmp_path):
    assert base_of(tmp_path, BRIEF).startswith("base main: the default branch, ")


@pytest.mark.parametrize(
    ("line", "base", "place"),
    [
        ("Stack: billing 1 on main", "main", "1"),
        ("Stack: billing 2 on add-schema", "add-schema", "2"),
    ],
)
def test_a_link_of_a_stack_opens_its_pull_request_on_the_branch_its_brief_names(
    line, base, place, tmp_path
):
    said = base_of(tmp_path, with_field(line))
    assert said.split(": ")[0] == f"base {base}"
    assert said.endswith(f"link {place} of the stack billing")
    assert ready.stack_of(with_field(line)) == "billing"


def test_only_a_stack_line_in_the_head_of_the_brief_gives_a_base(tmp_path):
    said = base_of(tmp_path, BRIEF + "Stack: billing 2 on add-schema\n")
    assert said.startswith("base main: the default branch, ")


@pytest.mark.parametrize(
    "line",
    [
        "Stack: billing",
        "Stack: billing 2",
        "Stack: billing 2 add-schema",
        "Stack: billing two on x",
    ],
)
def test_a_stack_line_that_names_no_branch_gives_no_base_to_guess(line, tmp_path):
    said = base_of(tmp_path, with_field(line))
    assert said.startswith("no base: the brief's Stack: line is not ")


def test_a_clone_that_does_not_know_the_default_branch_gives_no_base(tmp_path):
    said = base_of(tmp_path, BRIEF, knows_default=False)
    assert said.startswith("no base: the brief has no Stack: line, and ")


def test_a_link_whose_base_merged_moves_its_own_commits_onto_the_default_branch(tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    assert link.move() == ["moved from under onto origin/main"]
    assert not link.rebasing()
    assert git(link.work, "rev-parse", "HEAD~1") == link.landed
    assert git(link.work, "log", "--format=%s", "origin/main..HEAD") == "the link"
    assert (link.work / "under.txt").read_text() == "one\ntwo\n"

    review = merge.review("clean", before)
    assert covers(tmp_path / "main", BRIEF + review, link.head()) == (before, False)
    assert link.move() == ["already on origin/main: no rebase"]


def test_a_link_does_not_move_before_the_home_changed_its_base(tmp_path):
    link = Link(tmp_path, "under")
    before = link.head()
    assert link.move() == ["already on origin/under: no rebase"]
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()


def test_a_link_whose_parent_was_rewritten_under_it_is_rebased_from_where_it_started(tmp_path):
    link = Link(tmp_path, "under", under_moved=True)
    assert link.move() == ["moved from under onto origin/under"]
    assert not link.rebasing()
    assert git(link.work, "log", "--format=%s", "origin/under..HEAD") == "the link"


@pytest.mark.parametrize("mergeable", ["CONFLICTING", "MERGEABLE"])
def test_a_conflict_never_rebases_a_link_of_a_stack_by_itself(mergeable, tmp_path):
    link = Link(tmp_path, "main")
    view = f'{{"baseRefName": "main", "mergeable": "{mergeable}"}}'
    (link.stub / "view.json").write_text(view)
    before = link.head()
    (tmp_path / "tasks").mkdir()
    brief = tmp_path / "tasks" / "a-link.md"
    about = block("Stay on the pull request", "mergeable").replace("<slug>", "a-link")

    brief.write_text(with_field("Stack: billing 2 on under"))
    (said,) = link.run_text(about, H=str(tmp_path)).splitlines()
    assert said.startswith("a link of a stack: no rebase here")
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()
    brief.write_text(BRIEF + "Stack: billing 2 on under\n")
    said = link.run_text(about, H=str(tmp_path)).splitlines()
    if mergeable == "MERGEABLE":
        assert said == ["no conflict: no rebase"]
    else:
        stopped = "the rebase stopped: resolve these, then git rebase --continue"
        assert said == [stopped, "under.txt"]


def test_a_link_does_not_move_when_github_cannot_be_asked(tmp_path):
    link = Link(tmp_path, None)
    before = link.head()
    assert link.move() == ["could not ask GitHub: no rebase"]
    assert link.head() == before


def only_the_link_moved(link):
    return (
        git(link.work, "rev-parse", "HEAD~1") == link.landed
        and git(link.work, "log", "--format=%s", "origin/main..HEAD") == "the link"
        and not link.rebasing()
    )


def test_a_link_whose_parent_was_moved_before_it_merged_still_moves_only_its_own_commits(
    tmp_path,
):
    link = Link(tmp_path, "main", under_moved=True)
    assert git(link.work, "log", "--format=%s", "origin/under..HEAD").splitlines() == [
        "the link",
        "under, two",
        "under, one",
        "bottom, two",
        "bottom, one",
    ]
    assert link.move() == ["moved from under onto origin/main"]
    assert only_the_link_moved(link)


@pytest.mark.parametrize("under_moved", [False, True])
def test_a_link_does_not_move_once_the_branch_it_sat_on_is_gone(under_moved, tmp_path):
    link = Link(tmp_path, "main", under_moved=under_moved)
    before = link.head()
    git(link.work, "branch", "-q", "-D", "under")
    git(link.work, "push", "-q", "origin", "--delete", "under")
    (said,) = link.move()
    assert said.startswith("not found: the commit this branch started from is not under, ")
    assert said.endswith(": no rebase")
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()
    assert link.move(link.started_from) == [f"moved from {link.started_from} onto origin/main"]
    assert only_the_link_moved(link)


def test_a_link_does_not_move_from_a_commit_that_is_not_under_it(tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    git(link.work, "push", "-q", "origin", "--delete", "under")
    (said,) = link.move(link.landed)
    assert said.startswith("not found: ")
    assert link.head() == before


def test_a_move_that_conflicts_stops_and_says_which_files(tmp_path):
    link = Link(tmp_path, "main", edits="other.txt")
    said = link.move()
    assert said == ["the rebase stopped: resolve these, then git rebase --continue", "other.txt"]
    assert link.rebasing()
    assert link.move()[0] == "the rebase is not finished: resolve these, then git rebase --continue"
