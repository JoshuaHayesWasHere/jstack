"""A brief whose `Review:` line says `twice` gets one review, one fix round, and a second review
of the head that the fix pushed. It merges once the crew has answered the first review's
findings and pushed its `Fixed:` line, and the second reviewer has written its review. What that
review finds goes to a cleanup row (`jbus cleanup`) and never holds the merge. The tests drive
it through `ready.short_of`, the function that `jmerge` calls before a merge, and through
`jmerge` itself against a real origin and a fake `gh`
(`features/jmerge/tests/test_jmerge_fresh.py`).
"""

import jsettings
from jmerge import ready
from test_jmerge_fresh import LINES, Kitchen, url

HEAD, FIX = "a" * 40, "b" * 40
PULL = "https://example.test/pull/7"
WARNING = "warning a.py:3 the loop reads the list twice (bucket: Act on)"
INFO = "info b.py:9 a name says less than it could (bucket: Consider)"


def brief(mode="twice", result=""):
    return (
        f'# alpha: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n"
        f"Reviewer: mcp:9 #1\n{result}"
    )


def review(head, found=(WARNING,), verdict=None):
    verdict = verdict or ("findings" if found else "clean")
    listed = "".join(f"- {one}\n" for one in found) or "- none\n"
    return (
        f"\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\nVerdict: {verdict}\n"
        f"Head: {head}\nFindings:\n{listed}"
    )


def answered(fixed=FIX):
    """Write the first review, answer it in one fix round, and push the fix."""
    return f"Finding F1: fixed, the loop\nFixed: {fixed}\nSecond reviewer: mcp:10 #1\n"


def twice(second, fixed=FIX):
    return brief(result=answered(fixed)) + review(HEAD) + second


def test_a_clean_second_review_lets_it_merge():
    assert ready.short_of(twice(review(FIX, ())), FIX) == ""


def test_a_second_review_of_info_findings_alone_lets_it_merge():
    assert ready.short_of(twice(review(FIX, (INFO,))), FIX) == ""


def test_a_second_review_with_a_warning_lets_it_merge_and_its_findings_need_no_answer():
    text = twice(review(FIX, (WARNING, INFO)))
    assert ready.short_of(text, FIX) == ""
    assert ready.declines(text, user=jsettings.DEFAULTS) == ("", "")
    assert ready.to_range_diff(None, text, FIX) is None
    assert ready.under_fix(None, text, FIX) == ""
    review_mode = text.replace("Review: twice", "Review: review")
    assert ready.short_of(review_mode, FIX) == ready.NOT_PUSHED


def test_the_first_reviews_findings_left_unanswered_hold_it():
    unanswered = brief(result=f"Fixed: {FIX}\n") + review(HEAD) + review(FIX, ())
    assert ready.short_of(unanswered, FIX) == ready.UNANSWERED.format(ids="F1")
    uncited = unanswered.replace("Fixed:", "Finding F1: not fixed, the loop, because no\nFixed:")
    assert ready.short_of(uncited, FIX) == ready.UNCITED.format(ids="F1")


def test_it_waits_for_the_fix_round_and_then_for_the_second_review():
    assert ready.short_of(brief(), HEAD) == ready.NO_REVIEW
    assert ready.short_of(brief() + review(HEAD), HEAD) == ready.NO_FIXED
    assert ready.short_of(brief(result=answered(HEAD)) + review(HEAD), HEAD) == ready.NOT_PUSHED
    waiting = brief(result=answered()) + review(HEAD)
    assert ready.short_of(waiting, FIX) == ready.TWICE_UNWRITTEN.format(head=FIX[:12])
    not_run = twice(review(FIX, (), verdict="not run"))
    assert ready.short_of(not_run, FIX) == ready.TWICE_UNWRITTEN.format(head=FIX[:12])


def test_a_clean_first_review_or_a_round_that_pushed_nothing_owes_no_second_review():
    clean = brief(result="Fixed: none needed, clean\n") + review(HEAD, ())
    assert ready.short_of(clean, HEAD) == ""
    declined = "Finding F1: not fixed, the loop, because a.py:3 reads it once\n"
    nothing = brief(result=declined + "Fixed: none needed, declined\n") + review(HEAD)
    assert ready.short_of(nothing, HEAD) == ""


def test_a_first_section_that_did_not_run_is_not_the_first_review():
    """The reviewer wrote `Verdict: not run` and then ran again at a later head. That later run
    is the first review, so the fix it asks for still needs a second review."""
    again = brief(result=answered()) + review("c" * 40, (), verdict="not run") + review(HEAD)
    assert ready.short_of(again, FIX) == ready.TWICE_UNWRITTEN.format(head=FIX[:12])
    assert ready.short_of(again + review(FIX, ()), FIX) == ""


def test_a_twice_brief_asks_no_scoped_review_and_no_ruling_on_a_decline():
    """A fix outside `tests/` and a decline would make a `Review: review` brief need a scoped
    pass that rules on them. A twice brief needs only the second review."""
    declined = "Finding F1: not fixed, the loop, because a.py:3 reads it once\n"
    owed = "Scoped review: needed since " + HEAD + ", fix outside tests\n"
    text = brief(result=declined + f"Fixed: {FIX}\n" + owed) + review(HEAD) + review(FIX, ())
    assert ready.short_of(text, FIX) == ""
    assert ready.short_of(text.replace("Review: twice", "Review: review"), FIX) != ""


def test_a_twice_brief_still_owes_its_skills_and_the_crews_own_drop_lines():
    owed = twice(review(FIX, ())).replace("Review: twice", "Review: twice\nSkills: tdd")
    assert ready.short_of(owed, FIX) == ready.SKILLS_UNRUN.format(names="tdd")
    lost = (ready.Drop("a.py", 2, 0),)
    text = twice(review(FIX, ()))
    assert ready.drops(lost, text, FIX, user=jsettings.DEFAULTS)[0] == "wait"
    said = f"Dropped on rebase: a.py, 2 of main's, 0 of its own, at {FIX[:12]}: replaced\n"
    assert ready.drops(lost, text + said, FIX, user=jsettings.DEFAULTS) == ("", "")


def written(kitchen, slug, head, second):
    """The brief as a twice crewmate leaves it: its first review answered at the head that its
    fix pushed, and the second review of that head, written as `second` says."""
    pull = kitchen.pulls[slug]
    first = review("f" * 40)
    (kitchen.home.tasks / f"{slug}.md").write_text(
        f'# {slug}: a task\nTask: "do it"\nPull request: open one when done\nReview: twice\n\n'
        f"## Result\nStatus: done\nBranch: {slug}   Pull request: {pull['url']}\n"
        f"Reviewer: mcp:9 #1\n{answered(head)}{first}{second}"
    )


def test_jmerge_finds_it_ready_with_a_warning_in_its_second_review(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES})
    head = kitchen.crew("alpha", 7, {"a.txt": "ours\n" + LINES})
    written(kitchen, "alpha", head, "")
    reason = ready.TWICE_UNWRITTEN.format(head=head[:12])
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {reason}"]
    written(kitchen, "alpha", head, review(head, (WARNING, INFO)))
    (said,) = kitchen.run("--check")
    assert said == f"ready 7 {head} alpha alpha"
    assert kitchen.calls() == []
