"""The block of "A second pass" launches one scoped reviewer for a head, also when a run of it
was killed between the launch and its `Scoped reviewer:` line: the crew marks the launch in the
git dir first, and the next run finds that reviewer's thread before it gives a launch."""

import subprocess

import pytest

from crew_helpers import GUARDED, opened

OWED = "Scoped review: needed since {saw}, the review's Meets the brief line is no\n"
LAUNCHED = "scoped: the scoped reviewer is launched, and its findings come to this thread"


def mark(fix, head):
    """What the crew writes right before its `t3_thread_launch` call, as the section says."""
    found = subprocess.run(
        ["git", "rev-parse", "--git-path", "crew-scoped-launch"],
        cwd=fix.work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (fix.work / found).write_text(f"{head}\n")


@pytest.mark.parametrize("shell", ["sh", "bash"])
def test_a_run_after_a_kill_between_the_launch_and_its_line_launches_no_second_reviewer(
    shell, tmp_path
):
    fix = opened(tmp_path, GUARDED)
    owed = OWED.format(saw=fix.saw)
    message = f"/pr-review run alpha scoped {fix.start}..{fix.saw} {fix.start}..{fix.fixed}"
    assert fix.says(owed, shell=shell) == [f"scoped: launch the scoped reviewer, with {message}"]
    mark(fix, fix.fixed)
    assert fix.says(owed, shell=shell) == [
        "scoped: a launch of the scoped reviewer for this head began and wrote no "
        "Scoped reviewer: line: find its thread, `review: alpha, scoped` with the message "
        f"{message}, before you launch one"
    ]
    line = f"Scoped reviewer: mcp:3333-cccc, of {fix.fixed}\n"
    assert fix.says(owed + line, shell=shell) == [LAUNCHED]


def test_a_mark_of_an_earlier_head_holds_back_no_launch_at_this_one(tmp_path):
    fix = opened(tmp_path, GUARDED)
    owed = OWED.format(saw=fix.saw)
    mark(fix, fix.saw)
    assert fix.says(owed) == [
        "scoped: launch the scoped reviewer, with /pr-review run alpha scoped "
        f"{fix.start}..{fix.saw} {fix.start}..{fix.fixed}"
    ]
