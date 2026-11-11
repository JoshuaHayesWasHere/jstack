"""A crew whose Result says its pull request opens after the review waits on jbus while no
reviewer is launched, or one launched has not written a section that ran (`review.awaited`)."""

from jbus import review

BRIEF = "# alpha: a task\nReview: review\n\n## Result\nStatus: done\n"
RESULT = "## Result\nStatus: done\nBranch: alpha   Pull request: after the review\n"
RAN = "\n## Review\nBy: a b #1\nVerdict: clean\nHead: " + "a" * 40 + "\n"


def test_the_crew_waits_until_the_reviewer_it_was_given_has_written():
    assert review.awaited(BRIEF + RESULT, RESULT)
    assert review.awaited(BRIEF + "Reviewer: mcp:1 #1\n", RESULT)
    assert not review.awaited(BRIEF + "Reviewer: mcp:1 #1\n" + RAN, RESULT)
    assert not review.awaited(BRIEF, RESULT.replace("after the review", "none"))
