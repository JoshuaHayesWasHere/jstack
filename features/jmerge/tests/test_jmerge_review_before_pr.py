"""The review now comes before the pull request. The crew writes its Result once its desk proof
is on record, with `Pull request: after the review`, and pushes; jbus launches the reviewers and
adds their `Reviewer:` lines under that Result (`jbus.prereview`); each writes its `## Review`;
then the crew handles the findings, opens the pull request, and names it in a follow-up Result.
`jmerge` merges such a pull request on its required checks plus the review at its head, and waits
for each reviewer jbus launched. The tests run `jmerge` against the fake `gh` and real origin of
`test_home_merge`, over a brief in the order the crew, jbus and the reviewers write it."""

import pytest

import test_home_merge as merge
from jmerge import ready

HEAD = (
    '# alpha: a task\nTask: "do it"\nPull request: open one when done\n\n## Result\nStatus: done\n'
)
LAUNCHED = "Reviewer: mcp:review-1 #1\nReviewer: mcp:review-2 #2\n"


def before(head):
    """The brief as the crew left it at its desk proof, with the reviewers jbus launched."""
    proof = merge.desk_checked(head) + "Proved: none, docs\n"
    return HEAD + proof + "Branch: alpha   Pull request: after the review\nLeft: none\n" + LAUNCHED


def section(seat, head, verdict="clean", findings="none\n"):
    return (
        f"\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #{seat}\nVerdict: {verdict}\n"
        f"Head: {head}   Unchanged by the run: yes\nFindings:\n{findings}"
    )


def opened(more=""):
    return (
        "\n## Result, follow-up (2026-11-06, the pull request opened after its review)\n"
        f"Status: done\nBranch: alpha   Pull request: {merge.URL}\n{more}Left: none\n"
    )


@pytest.fixture
def merged(tmp_path):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    made.home.desk = False
    return made


def test_a_pull_request_opened_after_its_review_merges_on_its_checks_and_that_review(merged):
    head = merged.head
    (merged.home.tasks / "alpha.md").write_text(
        before(head) + section(1, head) + section(2, head) + opened()
    )
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_pull_request_opened_after_its_review_waits_for_each_reviewer_jbus_launched(merged):
    (merged.home.tasks / "alpha.md").write_text(
        before(merged.head) + section(1, merged.head) + opened()
    )
    (said,) = merged.run()
    assert said == f"wait 7 {merge.URL}: {ready.NO_VERDICT}"
    assert merged.untouched()


def test_a_review_before_the_pull_request_whose_findings_are_unanswered_holds_it(merged):
    found = "- [Act on] error a.py:1 it is wrong (proof: none)\n"
    text = (
        before(merged.head) + section(1, merged.head) + section(2, merged.head, "findings", found)
    )
    (merged.home.tasks / "alpha.md").write_text(text + opened())
    (said,) = merged.run()
    assert said.startswith(f"wait 7 {merge.URL}: its findings are not handled")
    answered = opened("Finding F1: not fixed, it is wrong, because a.py:1 is right as it is\n")
    (merged.home.tasks / "alpha.md").write_text(text + answered + "Fixed: none needed, declined\n")
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
