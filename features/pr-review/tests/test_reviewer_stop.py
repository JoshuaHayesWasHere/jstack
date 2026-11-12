"""A reviewer that stops before its review still writes the section that closes its seat, so the
brief does not read as `reviewing` after the reviewer is gone, as #1710's and #1708's did for hours.
The tests run the skill's blocks as a reviewer does, in the worktree `reviewer` gives.
"""

import crew_helpers as crew
from test_pr_review_skill import reviewer

__all__ = ["reviewer"]


def test_a_reviewer_that_cannot_fetch_closes_its_seat_at_the_worktrees_head(reviewer):
    """Start's step 2 stops where origin cannot be fetched, and a stop with no section left the
    reviewer's seat open and the brief `reviewing`, as #1710's did, until somebody noticed. The
    worktree's own commit is a head the section can name."""
    (reviewer.work / "a.py").write_text("one\n")
    crew.git(reviewer.work, "checkout", "-q", "-b", "a-task")
    crew.git(reviewer.work, "add", "-A")
    crew.git(reviewer.work, "commit", "-q", "-m", "the change")
    here = crew.git(reviewer.work, "rev-parse", "HEAD")
    (stop,) = reviewer.output("### Start", "git fetch -q origin")
    assert stop == f"stop: could not fetch origin's a-task and main, this worktree is at {here}"
    fill = {
        "<the head the review was to be of>": here,
        "<the stop line the step printed>": stop,
        "<the By: line Start printed>": "By: inherit #1",
    }
    assert reviewer.output("### A stop", fill=fill) == [
        f"written: ## Review with Verdict: not run, in {reviewer.brief}"
    ]
    assert reviewer.brief.read_text().endswith(
        f"Head: {here}   Unchanged by the review: not checked, no review ran\n"
        "Sent to: not sent, no review ran\n"
    )
