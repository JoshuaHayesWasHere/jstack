"""The crew skill's "A conflict": when a crewmate rebases onto a default branch that moved."""

import os
import subprocess

import pytest

import test_home_merge as merge
from crew_helpers import BRIEF, HAD, PullRequest, asked, block, covers, git, stays
from jmerge import ready

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


def main_adds(pr, other, name):
    """A commit on main adds a file, as a pull request that took the next migration number
    would."""
    pr.commit(other, name, "theirs\n", f"main adds {name}")
    git(other, "push", "-q", "origin", "HEAD:main")
    return git(other, "rev-parse", "HEAD")


def test_a_third_rebase_after_the_fixed_line_is_held_and_jmerge_waits_on_it(tmp_path):
    """This test covers upstream's cap on rebases. Past merge prep, when a change on trunk
    forces a third rebase, the block does not make it and reports it instead. The block
    counts the rebases it made after the `Fixed:` line and writes the stop line instead of
    making the third, and `jmerge` reads that line for the head it holds."""
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    brief = home / "tasks" / "alpha.md"
    brief.write_text(BRIEF)
    other = tmp_path / "other"

    def main_moves(name):
        pr.commit(other, name, "theirs\n", f"main changes {name}")
        git(other, "push", "-q", "origin", "HEAD:main")
        return git(other, "rev-parse", "HEAD")

    assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
    assert "Rebased after fixed:" not in brief.read_text()
    brief.write_text(brief.read_text() + f"Fixed: {pr.head()}\n")

    for name in ("second.txt", "third.txt"):
        before, tip = pr.head(), main_moves(name)
        assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
        assert git(pr.work, "rev-parse", "HEAD~1") == tip
        assert f"Rebased after fixed: {before} onto origin/main at {tip}\n" in brief.read_text()
    assert ready.rebase_held(brief.read_text(), pr.head()) == ""

    held, tip = pr.head(), main_moves("fourth.txt")
    third = "a third rebase after fixed and green"
    stop = f"Rebase hold: at {held}, {third}, onto origin/main at {tip}"
    told = [f"hold: no third rebase after fixed and green, the brief has the line {stop}"]
    assert pr.run("mergeable", home).splitlines() == told
    assert pr.head() == held
    assert not pr.rebasing()
    again = [f"held: no third rebase after fixed and green, and its gate is parked already: {stop}"]
    assert pr.run("mergeable", home).splitlines() == again
    assert brief.read_text().count("Rebase hold:") == 1
    assert brief.read_text().count("Rebased after fixed:") == 2
    assert ready.rebase_held(brief.read_text(), held) == ready.REBASE_HELD
    assert ready.rebase_held(brief.read_text(), tip) == ""

    brief.write_text(brief.read_text() + "Rebase hold lifted: question 7, by the user\n")
    assert ready.rebase_held(brief.read_text(), held) == ""
    assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
    assert brief.read_text().count("Rebased after fixed:") == 3


def test_a_renumber_rebase_counts_toward_the_cap_and_the_third_is_held(tmp_path):
    """When main has taken a migration's number, the crewmate rebases by running the block with
    `stale`, as the `renumber` message of `expedite` says to. GitHub reports no conflict. The
    block counts each such rebase after the `Fixed:` line, so it stops at the third rebase,
    and `jmerge` waits."""
    pr = PullRequest(tmp_path, "MERGEABLE", "0005_other.up.sql")
    asked(pr, "MERGEABLE")
    state = tmp_path / "home"
    brief = state / "tasks" / "a-task.md"
    other = tmp_path / "other"
    fixed = f"{BRIEF}Fixed: {pr.head()}\n"

    def renumber(text=None):
        return stays(pr, "mergeable", text, "stale", state=state)

    assert renumber(fixed) == ["rebased onto origin/main"]
    before, tip = pr.head(), main_adds(pr, other, "0006_other.up.sql")
    assert renumber() == ["rebased onto origin/main"]
    assert f"Rebased after fixed: {before} onto origin/main at {tip}\n" in brief.read_text()
    assert brief.read_text().count("Rebased after fixed:") == 2
    assert ready.rebase_held(brief.read_text(), pr.head()) == ""
    held, tip = pr.head(), main_adds(pr, other, "0008_other.up.sql")
    (said,) = renumber()
    assert said.startswith("hold: no third rebase after fixed and green")
    assert pr.head() == held
    assert ready.rebase_held(brief.read_text(), held) == ready.REBASE_HELD


def test_a_rebase_that_stops_after_the_fixed_line_counts_and_a_follow_up_counts_anew(tmp_path):
    """A follow-up with no `Fixed:` line of its own counts its rebases, and stops before it
    makes the third."""
    pr = PullRequest(tmp_path, "CONFLICTING", "shared.txt")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    brief = home / "tasks" / "alpha.md"
    before = pr.head()
    brief.write_text(BRIEF + f"Fixed: {before}\nRebased after fixed: {'e' * 40}\n")
    said = pr.run("mergeable", home).splitlines()
    assert said[0] == "the rebase stopped: resolve these, then git rebase --continue"
    assert pr.rebasing()
    counted = f"Rebased after fixed: {before} onto origin/main at {pr.landed}\n"
    assert brief.read_text().endswith(counted)
    git(pr.work, "rebase", "--abort")

    brief.write_text(brief.read_text() + "\n## Result, follow-up (a steer)\nStatus: done\n")
    for count in (3, 4):
        assert pr.run("mergeable", home).splitlines()[0].startswith("the rebase stopped")
        assert brief.read_text().count("Rebased after fixed:") == count
        git(pr.work, "rebase", "--abort")
    (third,) = pr.run("mergeable", home).splitlines()
    assert third.startswith("hold: no third rebase after fixed and green, the brief has the line ")
    assert brief.read_text().count("Rebased after fixed:") == 4
    assert not pr.rebasing()


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


THIRD = "a third rebase after fixed and green"


def rebased_twice(tmp_path, main_edits):
    """A made-up row: a pull request that is fixed and green and was rebased twice since, and a
    default branch that has moved under it once more."""
    pr = PullRequest(tmp_path, "CONFLICTING", main_edits)
    asked(pr, "CONFLICTING")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    twice = "".join(
        f"Rebased after fixed: {a * 40} onto origin/main at {b * 40}\n" for a, b in ("ab", "cd")
    )
    (home / "tasks" / "alpha.md").write_text(BRIEF + f"Fixed: {pr.head()}\n" + twice)
    return pr, home, home / "tasks" / "alpha.md"


def third_rebase(pr, home, resolved=None):
    """What the crewmate does on the conflict: the first block of "A conflict", the file the
    rebase stopped on resolved as `resolved` says, and the block that looks for lost lines."""
    said = pr.run("mergeable", home).splitlines()
    if resolved is not None:
        assert said[0] == "the rebase stopped: resolve these, then git rebase --continue"
        (pr.work / "shared.txt").write_text(resolved)
        git(pr.work, "add", "shared.txt")
        git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    else:
        assert said[0] == "rebased onto origin/main"
    assert said[-1].startswith(f"{THIRD}: run the block that looks for dropped lines")
    return pr.run("no rebase to look through", home).splitlines()


@pytest.mark.parametrize(
    ("main_edits", "resolved"),
    [
        ("other.txt", None),
        ("shared.txt", "theirs\nthe task\n"),
    ],
    ids=["a clean rebase", "a conflict resolved keeping both sides"],
)
def test_a_third_rebase_whose_range_diff_is_empty_goes_on_and_asks_nobody(
    main_edits, resolved, tmp_path
):
    """S10: a third rebase after fixed and green that leaves the reviewed content as it was
    goes by its default. No hold is written, so `jmerge` has nothing to wait on and no gate asks
    the user, and the rebase is counted in the brief as any other."""
    pr, home, brief = rebased_twice(tmp_path, main_edits)
    before = pr.head()
    said = third_rebase(pr, home, resolved)
    assert said[0].startswith(f"kept: {THIRD} whose range-diff is empty, so it goes on: ")
    assert said[-1].startswith("Kept: every line, in ")
    assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
    assert "Rebase hold:" not in brief.read_text()
    assert brief.read_text().endswith(
        f"Rebased after fixed: {before} onto origin/main at {pr.landed}\n"
    )
    assert brief.read_text().count("Rebased after fixed:") == 3
    assert ready.rebase_held(brief.read_text(), pr.head()) == ""
    assert ready.rebase_held(brief.read_text(), before) == ""
    assert (pr.git_dir / "crew-before-rebase").read_text().split() == [before, "main", before]
    assert pr.run("no rebase to look through", home).splitlines() == said[1:]


def test_a_third_rebase_that_changes_the_content_is_still_held_for_the_user(tmp_path):
    """S10: a third rebase after fixed and green whose resolution changed what was reviewed is
    not made. The head goes back to where it was, the resolved head is kept under a ref, and
    the hold line is written for that head, so `jmerge` waits and the gate asks the user."""
    pr, home, brief = rebased_twice(tmp_path, "shared.txt")
    before = pr.head()
    said = third_rebase(pr, home, "theirs\nthe task, as main has it now\n")
    resolved = git(pr.work, "rev-parse", f"refs/jstack/held-rebase/alpha/{before[:12]}")
    line = f"Rebase hold: at {before}, {THIRD}, onto origin/main at {pr.landed}"
    (hold,) = said
    assert hold.startswith(f"hold: {THIRD} changed the content, so it is not made: ")
    assert hold.endswith(f"; the brief has the line {line}")
    assert pr.head() == before
    assert git(pr.work, "rev-parse", f"{resolved}~1") == pr.landed
    assert not (pr.git_dir / "crew-before-rebase").exists()
    assert brief.read_text().endswith(line + "\n")
    assert brief.read_text().count("Rebased after fixed:") == 2
    assert ready.rebase_held(brief.read_text(), before) == ready.REBASE_HELD
    again = [f"held: no third rebase after fixed and green, and its gate is parked already: {line}"]
    assert pr.run("mergeable", home).splitlines() == again
    assert pr.head() == before


def test_three_rows_at_a_third_rebase_ask_the_user_once(tmp_path):
    """The replay of S10 from three made-up rows, each at its third rebase after fixed and
    green: two whose range-diff is empty go on by their default, and the one whose rebase
    changed the content still asks. What the user is asked is what `jmerge` holds."""
    rows = {
        "beta": ("other.txt", None),
        "gamma": ("shared.txt", "theirs\nthe task\n"),
        "delta": ("shared.txt", "theirs\nthe task, as main has it now\n"),
    }
    held = {}
    for slug, (main_edits, resolved) in rows.items():
        (tmp_path / slug).mkdir()
        pr, home, brief = rebased_twice(tmp_path / slug, main_edits)
        third_rebase(pr, home, resolved)
        held[slug] = ready.rebase_held(brief.read_text(), pr.head())
    assert held == {"beta": "", "gamma": "", "delta": ready.REBASE_HELD}
