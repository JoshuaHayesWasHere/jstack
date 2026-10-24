"""The crew skill's "A conflict": when a crewmate rebases onto a default branch that moved."""

import os
import subprocess

import pytest

import test_home_merge as merge
from crew_helpers import BRIEF, HAD, PullRequest, asked, block, covers, git

ANSWERS = [
    ("MERGEABLE", "no conflict: no rebase"),
    ("UNKNOWN", "GitHub has not decided yet: no rebase"),
    (None, "could not ask GitHub: no rebase"),
]


@pytest.mark.parametrize(("mergeable", "says"), ANSWERS)
@pytest.mark.parametrize("main_edits", ["other.txt", "shared.txt"])
def test_a_default_branch_that_moved_is_not_rebased_onto(mergeable, says, main_edits, tmp_path):
    pr = PullRequest(tmp_path, mergeable, main_edits)
    before = pr.head()
    assert pr.run("mergeable").splitlines() == [says]
    assert pr.head() == before
    assert not pr.rebasing()
    assert not (pr.git_dir / "crew-before-rebase").exists()


def test_a_rebase_that_cannot_start_is_not_reported_as_one(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    git(pr.work, "config", "rebase.autoStash", "false")
    (pr.work / "shared.txt").write_text("an edit not committed\n")
    said = pr.run("mergeable")
    assert said.splitlines()[0] == "the rebase did not start: no rebase"
    assert "unstaged changes" in said
    assert pr.head() == before
    assert not pr.rebasing()
    assert not (pr.git_dir / "crew-before-rebase").exists()


def test_an_origin_that_cannot_be_reached_is_not_reported_as_a_rebase(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    git(pr.work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    assert pr.run("mergeable").splitlines() == ["could not fetch origin/main: no rebase"]
    assert pr.head() == before
    assert not (pr.git_dir / "crew-before-rebase").exists()


def test_a_conflict_that_rebases_cleanly_leaves_a_record_of_the_head_before_it(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    pr.run("mergeable")
    assert pr.head() != before
    assert not pr.rebasing()
    assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
    assert (pr.git_dir / "crew-before-rebase").read_text().split() == [before, "main"]


def test_a_conflict_that_does_not_resolve_is_reported_and_then_its_changes_are(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "shared.txt")
    before = pr.head()
    said = pr.run("mergeable")
    assert pr.rebasing()
    assert "shared.txt" in said.splitlines()
    assert "git rebase --continue" in said
    record = (pr.git_dir / "crew-before-rebase").read_text()
    again = pr.run("mergeable")
    assert "not finished" in again
    assert "shared.txt" in again.splitlines()
    assert (pr.git_dir / "crew-before-rebase").read_text() == record
    assert record.split() == [before, "main"]

    (pr.work / "shared.txt").write_text("theirs\nthe task\n")
    git(pr.work, "add", "shared.txt")
    git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert not pr.rebasing()
    assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
    assert (pr.git_dir / "crew-before-rebase").read_text() == record


def test_a_conflict_is_rebased_while_a_second_pass_is_still_needed(tmp_path):
    """Nothing refuses a rebased head, so neither the rebase nor the second pass waits, and the
    second pass reviews the head it is given."""
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    saw = pr.head()
    pr.commit(pr.work, "wider.txt", "the fix\n", "the fix")
    git(pr.work, "push", "-q", "origin", "a-task")
    state = tmp_path / "state"
    (state / "tasks").mkdir(parents=True)

    def review(head):
        found = "Findings:\n- warning shared.txt:2 it runs twice\nDropped: 0\n"
        return f"\n## Review\nVerdict: findings\nHead: {head}\n{found}"

    def second_pass(result, reviews):
        (state / "tasks" / "alpha.md").write_text(BRIEF + result + reviews)
        ran = subprocess.run(
            ["sh", "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=pr.work,
            env={**os.environ, "H": str(state)},
            check=True,
        )
        return ran.stdout.splitlines()

    owed = f"Scoped review: needed since {saw}, the fix changed wider.txt\n"
    assert second_pass("", review(saw)) == [f"write {owed.strip()}"]
    (asked,) = second_pass(owed, review(saw))
    assert asked.startswith("scoped: launch the scoped reviewer, with ")
    assert f"..{saw} " in asked and asked.endswith(f"..{pr.head()}")
    needed = f"Second pass: needed since {saw}, the fix also changed wider.txt\n"
    launch = ["needed: launch the second reviewer"]
    assert second_pass(needed, review(saw)) == launch
    fixed = pr.head()
    assert pr.run("mergeable").splitlines() == ["rebased onto origin/main"]
    assert pr.head() != fixed
    assert git(pr.work, "rev-parse", "HEAD~2") == pr.landed
    assert second_pass(needed, review(saw)) == launch
    (asked,) = second_pass(owed, review(saw))
    assert asked.endswith(f"..{saw} {pr.landed}..{pr.head()}")
    assert second_pass(owed, review(saw) + review(pr.head())) == [HAD]
    launched = needed + "Second reviewer: mcp:2222-bbbb\n"
    assert second_pass(launched, review(saw) + review(pr.head())) == [
        "had: the second pass is written, and it is the last"
    ]


@pytest.mark.parametrize("main_edits", ["other.txt", "shared.txt"])
@pytest.mark.parametrize("fixed", [False, True])
def test_a_rebase_that_wrote_no_line_is_one_jmerge_carries_the_review_over(
    main_edits, fixed, tmp_path
):
    """The Result is as it was before the rebase: no `Rebase:` line, and a `Fixed:` line that
    names the commit it named then."""
    pr = PullRequest(tmp_path, "CONFLICTING", main_edits)
    saw = pr.head()
    pr.commit(pr.work, "mine.txt", "the task\n", "more of the task")
    before = pr.head()
    pr.run("mergeable")
    if pr.rebasing():
        (pr.work / "shared.txt").write_text("theirs\nthe task\n")
        git(pr.work, "add", "shared.txt")
        git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert pr.head() != before
    handled = f"Finding: fixed, it is wrong\nFixed: {before}\n" if fixed else ""
    review = merge.review("findings" if fixed else "clean", saw if fixed else before)
    assert covers(tmp_path / "main", BRIEF + handled + review, pr.head()) == (before, True)


@pytest.mark.parametrize(
    ("main_edits", "resolved", "clean"),
    [
        ("other.txt", None, True),
        ("shared.txt", "theirs\nthe task\n", True),
        ("shared.txt", "theirs\nthe task\nand a line the resolution adds\n", False),
    ],
    ids=["a clean rebase", "a conflict resolved keeping both sides", "a resolution that adds"],
)
def test_a_third_rebase_after_fixed_and_green_is_pushed_and_its_change_is_reviewed(
    main_edits, resolved, clean, tmp_path
):
    """Bugs 5 and 6 of fl-statechart: a third rebase after fixed and green goes on as the two
    before it did, whatever its range-diff. Nothing is held and nobody is asked: where the
    rebase left the reviewed content as it was the review carries over, and where it changed it
    `jmerge` waits on the scoped review of the changed range, as after a second rebase."""
    pr = PullRequest(tmp_path, "CONFLICTING", main_edits)
    saw = pr.head()
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    git(pr.work, "push", "-q", "origin", "a-task")
    asked(pr, "CONFLICTING")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    before = pr.head()
    twice = "".join(
        f"Rebased after fixed: {a * 40} onto origin/main at {b * 40}\n" for a, b in ("ab", "cd")
    )
    brief = home / "tasks" / "alpha.md"
    brief.write_text(BRIEF + f"Fixed: {before}\n" + twice)
    written = brief.read_text()

    said = pr.run("mergeable", home).splitlines()
    if resolved is None:
        assert said == ["rebased onto origin/main"]
    else:
        assert said[0] == "the rebase stopped: resolve these, then git rebase --continue"
        (pr.work / "shared.txt").write_text(resolved)
        git(pr.work, "add", "shared.txt")
        git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    (kept,) = pr.run("no rebase to look through", home).splitlines()
    assert kept.startswith("Kept: every line, in ")
    assert pr.run("--force-with-lease", home).splitlines() == [f"pushed {pr.head()} over {before}"]
    assert git(pr.work, "rev-parse", "origin/a-task") == pr.head()
    assert git(pr.work, "rev-parse", "HEAD~2") == pr.landed
    assert brief.read_text() == written

    judged = (
        BRIEF + f"Finding: fixed, it is wrong\nFixed: {before}\n" + merge.review("findings", saw)
    )
    assert covers(tmp_path / "main", judged, pr.head()) == (before, clean)
