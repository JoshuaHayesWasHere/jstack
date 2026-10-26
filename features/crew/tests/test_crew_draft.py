"""A crew opens its pull request as a draft, and CI runs no check on a draft (check.yml). It marks
the pull request ready once, when its fix round is pushed, so its check runs once, on the head
that goes to the merge gate. A brief that owes this thread no fix round, `Review: none` or
`Review: after`, is marked ready at once. A link stacked on another row's branch stays a draft:
jbus marks it ready when it moves it onto the default branch.

Each test runs the skill's block as an agent runs it, in a worktree whose remote's default
branch is `main`, against a `gh` that answers from a file and logs what it was asked."""

import json
import os
import subprocess

import pytest

from crew_helpers import BRIEF, block, git, with_field
from testing.layouts import assembled

HEAD = "c" * 40
GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
case "$1 $2" in
    "pr view") cat "$STUB/view.json" ;;
    "pr ready") [ ! -e "$STUB/refused" ] ;;
    *) exit 64 ;;
esac
"""
FIXED = BRIEF + f"Fixed: {HEAD}\n"


@pytest.fixture
def ready(tmp_path):
    """Run the block for a brief and a pull request as GitHub gives it, and return what it
    printed and what it asked `gh`."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "alpha")
    git(work, "commit", "-q", "--allow-empty", "-m", "the task")
    git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "gh").write_text(GH)
    (stub / "gh").chmod(0o755)
    (tmp_path / "tasks").mkdir()

    def said(brief, draft=True, base="main"):
        (tmp_path / "tasks" / "alpha.md").write_text(brief)
        view = {"isDraft": draft, "baseRefName": base, "headRefOid": HEAD}
        (stub / "view.json").write_text(json.dumps(view))
        (stub / "calls").write_text("")
        ran = subprocess.run(
            ["sh", "-c", block("The review", "gh pr ready").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=work,
            env={
                **os.environ,
                "PATH": f"{stub}:{os.environ['PATH']}",
                "STUB": str(stub),
                "H": str(tmp_path),
                "T": str(assembled() / "templates"),
            },
            check=True,
        )
        asked = [line for line in (stub / "calls").read_text().splitlines() if line]
        return ran.stdout.splitlines(), [line for line in asked if line.startswith("pr ready")]

    said.stub = stub
    return said


def test_a_draft_stays_one_until_its_fix_round_is_pushed(ready):
    said, readied = ready(BRIEF)
    assert said[0].startswith("draft: ") and readied == []


def test_a_draft_into_main_is_marked_ready_once_its_fixed_line_is_written(ready):
    said, readied = ready(FIXED)
    assert said == [f"ready: marked ready at {HEAD}, so CI runs its check once, on this head"]
    assert readied == ["pr ready"]
    said, readied = ready(BRIEF + "Fixed: none needed, a clean review\n")
    assert said[0].startswith("ready: marked ready at ") and readied == ["pr ready"]


@pytest.mark.parametrize("mode", ["none", "after"])
def test_a_brief_that_owes_this_thread_no_fix_round_is_marked_ready_at_once(ready, mode):
    said, readied = ready(with_field(f"Review: {mode}"))
    assert said[0].startswith("ready: marked ready at ") and readied == ["pr ready"]


@pytest.mark.parametrize("mode", ["review", "twice"])
def test_a_brief_whose_review_this_thread_answers_waits_for_its_fixed_line(ready, mode):
    said, readied = ready(with_field(f"Review: {mode}"))
    assert said[0].startswith("draft: ") and readied == []


def test_a_link_stacked_on_another_rows_branch_stays_a_draft_for_jbus_to_mark(ready):
    said, readied = ready(FIXED, base="other-row")
    assert said == [
        "draft: its base is other-row, and jbus marks it ready when it moves it onto main"
    ]
    assert readied == []


def test_a_pull_request_marked_ready_already_is_left_as_it_is(ready):
    said, readied = ready(FIXED, draft=False)
    assert said == ["ready: it is marked ready, and CI runs its check on each push"]
    assert readied == []


def test_a_mark_that_github_refuses_is_said_and_not_taken_for_done(ready):
    (ready.stub / "refused").write_text("")
    said, readied = ready(FIXED)
    assert said == ["wait: gh pr ready did not mark it ready"] and readied == ["pr ready"]
