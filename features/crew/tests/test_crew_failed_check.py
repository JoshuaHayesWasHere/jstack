"""The crew skill's "A failed check" tells the change's own failure from a stale base or a
flake."""

import re

import pytest

from crew_helpers import BRIEF, Failed, git, run, spent
from testing.paths import REPO


def in_the_template(line):
    """Whether a line that a block printed is the template's line of that label. The block must
    fill in each of the template's `<...>`, and must leave off the template's note of when the
    line appears."""
    template = (REPO / "features" / "crew" / "templates" / "result.md").read_text()
    (written,) = [text for text in template.splitlines() if text.split()[0] == line.split()[0]]
    shape, holes = written.split("   <")[0], 1
    while holes:
        shape, holes = re.subn(r"<[^<>]*>", "\0", shape)
    return bool(re.fullmatch(re.escape(shape).replace("\0", ".+"), line))


@pytest.mark.parametrize("holds_base", [True, False])
def test_a_failure_the_check_command_shows_here_is_the_changes_own(holds_base, tmp_path):
    failed = Failed(tmp_path, holds_base)
    assert failed.says("failed").split(": ")[0] == "fix"
    assert failed.reruns() == []


def test_with_github_s_budget_at_its_floor_the_block_asks_nothing_and_is_held(tmp_path):
    failed = Failed(tmp_path)
    spent(failed.stub)
    said = failed.says("passed", wait=0)
    assert said.startswith("held: GitHub's core budget has 0 of 5000 calls left")
    assert failed.reruns() == []


def test_a_failure_that_is_not_the_changes_on_a_branch_behind_its_base_is_a_stale_base(tmp_path):
    failed = Failed(tmp_path, holds_base=False)
    head = failed.head()
    said = failed.says("passed")
    assert said.split(": ")[0] == "stale"
    assert "origin/main" in said
    assert failed.reruns() == []
    assert failed.head() == head
    assert not failed.rebasing()
    assert git(failed.work, "status", "--porcelain") == ""


def test_any_other_failure_gets_one_fresh_run_of_the_whole_workflow_run(tmp_path):
    failed = Failed(tmp_path)
    failed.push([run("FAILURE", 2), run("TIMED_OUT", 3), run("SUCCESS", 4)])
    said = failed.says("passed")
    assert said.split(": ")[0] == "rerun"
    assert failed.reruns() == ["run rerun 5"]

    line = failed.brief.read_text().splitlines()[-1]
    assert line == f"Rerun: at {failed.head()}, workflow run 5 was run again whole"
    assert said.endswith(line)
    assert in_the_template(line)


def test_a_second_failure_at_a_head_is_not_a_flake_and_one_at_a_new_head_may_be(tmp_path):
    failed = Failed(tmp_path)
    assert failed.says("passed").split(": ")[0] == "rerun"
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == ["run rerun 5"]

    git(failed.work, "commit", "-q", "--allow-empty", "-m", "a fix")
    failed.push()
    assert failed.says("passed").split(": ")[0] == "rerun"
    assert failed.reruns() == ["run rerun 5", "run rerun 5"]


def test_the_rerun_is_recorded_as_a_line_of_its_own_in_a_brief_with_no_last_newline(tmp_path):
    failed = Failed(tmp_path)
    failed.brief.write_text(BRIEF + "\n## Review\nHead: " + "a" * 40)
    assert failed.says("passed").split(": ")[0] == "rerun"
    last, line = failed.brief.read_text().splitlines()[-2:]
    assert last == "Head: " + "a" * 40
    assert line.startswith(f"Rerun: at {failed.head()}, ")
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == ["run rerun 5"]


def test_a_rerun_the_brief_cannot_record_is_not_said_to_be_recorded(tmp_path):
    failed = Failed(tmp_path)
    failed.brief.chmod(0o444)
    said = failed.says("passed")
    assert said.split(": ")[0] == "wait"
    assert said.endswith(
        f"add the line Rerun: at {failed.head()}, workflow run 5 was run again whole"
    )
    assert failed.brief.read_text() == BRIEF


def test_a_failed_check_that_is_no_workflow_run_has_nothing_to_run_again(tmp_path):
    failed = Failed(tmp_path)
    failed.push([{"__typename": "StatusContext", "state": "FAILURE"}, run("FAILURE")])
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == []


def not_told(failed):
    return None


def not_pushed(failed):
    git(failed.work, "commit", "-q", "--allow-empty", "-m", "not pushed")
    return "passed"


def not_committed(failed):
    (failed.work / "new.txt").write_text("more\n")
    return "failed"


def no_github(failed):
    (failed.stub / "view.json").unlink()
    return "passed"


def no_origin(failed):
    git(failed.work, "remote", "set-url", "origin", str(failed.stub / "gone.git"))
    return "passed"


def no_rerun(failed):
    (failed.stub / "no-rerun").write_text("")
    return "passed"


@pytest.mark.parametrize(
    "kept", [not_told, not_pushed, not_committed, no_github, no_origin, no_rerun]
)
def test_a_failed_check_the_block_cannot_judge_waits_and_changes_nothing(kept, tmp_path):
    failed = Failed(tmp_path)
    here = kept(failed)
    assert failed.says(here).split(": ")[0] == "wait"
    assert failed.reruns() == (["run rerun 5"] if kept is no_rerun else [])
    assert "Rerun:" not in failed.brief.read_text()


def test_a_worktree_behind_a_head_jmerge_merged_its_base_into_is_told_to_fast_forward(tmp_path):
    """jmerge asked GitHub to merge the base into the branch, so the pushed head is a commit
    ahead of this worktree, and a push from here would be refused."""
    failed = Failed(tmp_path, holds_base=False)
    was = failed.head()
    git(failed.work, "fetch", "-q", "origin")
    git(failed.work, "merge", "-q", "--no-edit", "origin/main")
    git(failed.work, "push", "-q", "origin", "HEAD")
    failed.push()
    merged = failed.head()
    git(failed.work, "reset", "-q", "--hard", was)
    said = failed.says("passed")
    assert said.split(": ")[0] == "wait"
    assert f"git merge --ff-only {merged}" in said
    assert failed.head() == was and failed.reruns() == []
