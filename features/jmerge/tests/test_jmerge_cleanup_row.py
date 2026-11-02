"""The day's warnings row, which jbus files (`jbus.daywarnings`), says `Review: cleanup`. It gets
one review, of its own diff, in which only an error goes to its crew, whatever its bucket or tag:
a warning and an info are dropped, so none of its findings is kept for another day's row and no
follow-up of a follow-up is queued. A fix for its errors gets no scoped review and no ruling, and
it merges on its checks. The tests drive it through `ready.short_of`, the function `jmerge` calls
before a merge, and through `jbriefs.findings.triage`, which jbus reads to collect a day's
warnings."""

import pytest

from jbriefs import findings
from jmerge import ready
from test_jmerge_later_review import ERROR, FIX, HEAD, INFO, PULL, RISKY, WARNING, review


def brief(result=""):
    return (
        f"# warnings-2026-11-01: fix the warnings later reviews found\nTask: the warnings\n"
        f"Decisions: {findings.CLEANUP_DECIDED}of 2026-11-01\n"
        "Pull request: open one when done\nReview: cleanup\n\n"
        f"## Result\nStatus: done\nBranch: warnings-2026-11-01   Pull request: {PULL}\n"
        f"Reviewer: mcp:9 #1\n{result}"
    )


@pytest.mark.parametrize("found", [(WARNING,), (RISKY,), (INFO,), (WARNING, INFO), ()])
def test_its_one_review_with_no_error_holds_nothing_and_keeps_nothing(found):
    text = brief() + review(HEAD, found)
    assert ready.short_of(text, HEAD) == ""
    said = findings.triage(text)
    assert all(one.route == findings.DROPPED for one in said.findings)
    assert said.routed(findings.KEPT) == []
    assert findings.fixed_shape(said) is None


def test_its_error_holds_until_it_is_fixed_pushed_and_answered_and_no_review_follows():
    found = (ERROR, WARNING, INFO)
    assert ready.short_of(brief(), HEAD) == ready.NO_REVIEW
    assert ready.short_of(brief() + review(HEAD, found), HEAD) == ready.NO_FIXED
    pushed = brief(f"Fixed: {FIX}\n") + review(HEAD, found)
    assert ready.short_of(pushed, FIX) == ready.UNANSWERED.format(ids="F1")
    answered = brief(f"Finding F1: fixed, the retry\nFixed: {FIX}\n") + review(HEAD, found)
    assert ready.short_of(answered, FIX) == ""
    assert ready.asks_no_ruling(answered)
    assert ready.to_range_diff(answered, FIX) is None
    routes = [one.route for one in findings.triage(answered).findings]
    assert routes == [findings.HOLDS, findings.DROPPED, findings.DROPPED]


def test_a_later_section_of_its_review_keeps_no_warning_either():
    text = brief(f"Finding F1: fixed, the retry\nFixed: {FIX}\n") + review(HEAD, (ERROR,))
    text += review(FIX, (WARNING,), f"x..{HEAD} x..{FIX}")
    said = findings.triage(text)
    assert said.routed(findings.KEPT) == []
    assert ready.short_of(text, FIX) == ""
