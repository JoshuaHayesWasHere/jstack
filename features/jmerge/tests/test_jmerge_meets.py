"""`jmerge` reads the reviewer's judgement of the brief, the typed `Meets the brief:` line, and a
pull request whose last round says the brief is not met does not merge (`jbriefs.meets`). The
week audit found 44 rows merged while their last review said `Meets the brief: no`, since no
code read the line. The tests run through `ready.short_of`, the function `jmerge` judges a pull
request with, over briefs as the skills write them."""

import pytest

from jbriefs import meets
from jmerge import ready

SAW, FIX, LATER = "a" * 40, "b" * 40, "c" * 40
DONE = "Done when:\n- the rule holds: a test\n- the docs say it\n- the check command passes\n"
HEAD = f"# alpha: a task\nTask: do it\n{DONE}Review: review\n"
RESULT = (
    "\n## Result\nStatus: done\nBranch: alpha   Pull request: https://example.test/pull/7\n"
    "Reviewer: mcp:9 #1\n"
)
YES = "Meets the brief: yes, 3 of 3"
NO = "Meets the brief: no, 2 of 3\n- unmet 2: the docs say it"
ERROR = "error a.py:1 the docs are not written (principle: none) (bucket: Act on)"


def section(meets, head=SAW, verdict="clean", findings=("none",), scoped=False, by="inherit #1"):
    listed = "".join(f"- {one}\n" for one in findings)
    scope = f"Scope: range-diff {SAW}..{SAW} {SAW}..{head}\n" if scoped else ""
    line = f"{meets}\n" if meets else ""
    return (
        f"\n## Review\nBy: {by}\nVerdict: {verdict}\n{scope}Head: {head}   Unchanged by the "
        f"review: yes\n{line}In flight: none\nFindings:\n{listed}Dropped: 0\n"
    )


def brief(*sections, head=HEAD, result=""):
    return head + RESULT + result + "".join(sections)


def test_a_last_round_that_says_no_holds_the_merge_by_its_own_reason():
    held = ready.short_of(brief(section(NO)), SAW)
    assert held == ready.MEETS_NO.format(head=SAW[:12], met=2, count=3, lines="2")
    assert ready.code_of(held) == "meets-no"
    assert ready.step_of("meets-no") == "findings"
    assert ready.short_of(brief(section(YES)), SAW) == ""


@pytest.mark.parametrize(
    "line",
    [
        "",
        "Meets the brief: yes",
        "Meets the brief: no, the docs are not written",
        "Meets the brief: yes, 2 of 3",
        "Meets the brief: no, 2 of 3",
        "Meets the brief: no, 1 of 3\n- unmet 2: the docs say it",
        "Meets the brief: yes, 3 of 3\n- unmet 2: the docs say it",
        "Meets the brief: no, 2 of 3\n- unmet 4: a line the brief does not have",
    ],
    ids=[
        "no line",
        "free text yes",
        "free text no",
        "a yes short of its count",
        "a no that names no line",
        "a no whose count and lines disagree",
        "a yes that names an unmet line",
        "a line number past the count",
    ],
)
def test_a_round_with_no_line_jmerge_can_read_holds_the_merge(line):
    held = ready.short_of(brief(section(line)), SAW)
    assert held == ready.MEETS_UNREAD.format(head=SAW[:12])
    assert ready.step_of(ready.code_of(held)) == "review"


def test_a_round_whose_count_is_not_the_briefs_holds_the_merge():
    held = ready.short_of(brief(section("Meets the brief: yes, 4 of 4")), SAW)
    assert held == ready.MEETS_MISCOUNTED.format(head=SAW[:12], said=4, count=3)
    assert ready.code_of(held) == "meets-miscounted"


def test_a_line_waiting_on_ci_or_only_provable_after_the_merge_is_not_unmet():
    line = (
        "Meets the brief: yes, 3 of 3\n- waiting 3: the check command passes\n"
        "- after-merge 1: the rule holds: a test"
    )
    assert ready.short_of(brief(section(line)), SAW) == ""
    line = "Meets the brief: no, 2 of 3\n- waiting 3: the check command passes\n- unmet 2: docs"
    assert ready.short_of(brief(section(line)), SAW) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="2"
    )


def test_review_none_no_review_section_and_a_brief_with_no_done_when_list_are_unchanged():
    none = HEAD.replace("Review: review", "Review: none")
    assert ready.short_of(brief(head=none), SAW) == ready.REVIEW_NONE
    assert ready.short_of(brief(section(NO), head=none), SAW) == ready.REVIEW_NONE
    assert ready.short_of(brief(), SAW) == ready.NO_REVIEW
    listless = HEAD.replace(DONE, "")
    assert ready.short_of(brief(section(""), head=listless), SAW) == ""


def test_the_way_out_is_a_fix_and_a_scoped_review_whose_own_line_says_yes():
    """The first round's `no` owes the crew a push and the scoped review of it, by the path
    findings take. The scoped pass re-judges the line the `no` named and carries the rest, and
    its `yes` at the head the fix pushed clears the `no`: a stale first-round `no` is not read."""
    first = section(NO, verdict="findings", findings=[ERROR])
    fixed = (
        "Finding F1: fixed, the docs are written\n"
        f"Scoped review: needed since {SAW}, the review says the brief is not met\n"
        f"Fixed: {FIX}\n"
    )
    assert ready.short_of(brief(first), SAW) == ready.NO_FIXED
    assert ready.short_of(brief(first, result=fixed), FIX) == ready.FIX_UNREVIEWED
    scoped = section(YES, head=FIX, scoped=True)
    assert ready.short_of(brief(first, scoped, result=fixed), FIX) == ""
    unread = section("", head=FIX, scoped=True)
    assert ready.short_of(brief(first, unread, result=fixed), FIX) == (
        ready.MEETS_UNREAD.format(head=FIX[:12])
    )
    again = section(NO, head=FIX, scoped=True)
    assert ready.short_of(brief(first, again, result=fixed), FIX) == ready.MEETS_NO.format(
        head=FIX[:12], met=2, count=3, lines="2"
    )


def test_a_scoped_pass_at_the_same_head_rules_after_the_no_and_its_yes_clears_it():
    """Nothing pushed: the crew declined the finding behind the `no`, and the scoped pass that
    rules on the decline at the same head is the later round."""
    first = section(NO, verdict="findings", findings=[ERROR])
    declined = (
        "Finding F1: not fixed, the docs are written, because `docs/a.md:3` has them\n"
        f"Scoped review: needed since {SAW}, to rule on the declines of F1\n"
        "Fixed: none needed, declined\n"
    )
    ruled = section(YES, scoped=True).replace("Head:", "Declines: upheld F1\nHead:")
    assert ready.short_of(brief(first, result=declined), SAW) == ready.FIX_UNREVIEWED
    assert ready.short_of(brief(first, ruled, result=declined), SAW) == ""


def test_a_later_full_round_at_a_later_head_takes_the_place_of_an_earlier_no():
    later = section(YES, head=LATER)
    assert ready.short_of(brief(section(NO), later), LATER) == ""
    assert ready.short_of(brief(section(YES), section(NO, head=LATER)), LATER) == (
        ready.MEETS_NO.format(head=LATER[:12], met=2, count=3, lines="2")
    )


def test_each_reviewer_of_the_last_round_must_say_yes():
    two = "Reviewer: mcp:8 #2\n"
    both = brief(section(YES), section(NO, by="codex gpt-6 xhigh #2"), result=two)
    assert ready.short_of(both, SAW) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="2"
    )


WAIVED = "Waived: the docs say it, mcp:josh/m1\n"


def test_a_waiver_on_a_word_the_caller_checked_clears_the_line_it_names():
    held = brief(section(NO), result=WAIVED)
    assert ready.short_of(held, SAW, heard=set(meets.waivers(held))) == ""
    assert ready.short_of(held, SAW) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="2"
    )
    other = {meets.Waiver(3, "mcp:josh/m1", "the check command passes")}
    assert ready.short_of(held, SAW, heard=other) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="2"
    )


def test_a_waiver_names_its_line_whole_or_by_a_start_no_other_line_has():
    by_start = brief(section(NO), result="Waived: The docs, mcp:josh/m1\n")
    assert ready.short_of(by_start, SAW, heard=set(meets.waivers(by_start))) == ""
    two = "Meets the brief: no, 1 of 3\n- unmet 2: docs\n- unmet 3: check"
    other = brief(section(two), result="Waived: the, mcp:josh/m1\n" + WAIVED)
    assert ready.short_of(other, SAW, heard=set(meets.waivers(other))) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="3"
    )


def test_a_waiver_that_names_its_line_by_part_of_a_word_names_none():
    """brief-verdict-gate F6: a start cut inside a word, `the d`, is a few letters any word
    about the row may hold, so it names no line."""
    assert meets.waivers(brief(section(NO), result="Waived: the d, mcp:josh/m1\n")) == ()


def test_a_cleanup_brief_is_held_by_its_review_saying_no():
    cleanup = HEAD.replace("Review: review", "Review: cleanup")
    assert ready.short_of(brief(section(NO), head=cleanup), SAW) == ready.MEETS_NO.format(
        head=SAW[:12], met=2, count=3, lines="2"
    )
    assert ready.short_of(brief(section(YES), head=cleanup), SAW) == ""


class Bus:
    """The bus there is, but for the waivers: `heard` answers `said` and keeps what it was asked."""

    def __init__(self, real, said):
        self.real, self.said, self.asked = real, said, []

    def heard(self, checkout, waiver, slug):
        self.asked.append((waiver, slug))
        return self.said

    def __getattr__(self, name):
        return getattr(self.real, name)
