"""A brief whose role map lists two reviewers gets a `## Review` section from each, both of
one head: `jmerge` reads them as one round. The round waits for every reviewer the
`Reviewer:` lines name, and its verdict is the worst of its sections. Run through
`ready.short_of`, the reader the merge goes by, over briefs as the skills write them."""

from jmerge import ready

SAW, FIX = "a" * 40, "b" * 40
RESULT = "\n## Result\nStatus: done\nBranch: alpha   Pull request: https://example.test/pull/7\n"
TWO = "Reviewer: mcp:codex-1\nReviewer: mcp:cursor-2\n"


def section(by, verdict, head=SAW, findings=("none",)):
    listed = "".join(f"- {one}\n" for one in findings)
    return f"\n## Review\nBy: {by}\nVerdict: {verdict}\nHead: {head}\nFindings:\n{listed}"


CODEX = "codex gpt-6-sol xhigh"
CURSOR = "cursor grok-4.7 xhigh"


def test_one_of_two_reviewers_written_is_a_review_with_no_verdict_yet():
    brief = RESULT + TWO + section(CODEX, "clean")
    assert ready.short_of(brief, SAW) == ready.NO_VERDICT
    assert ready.short_of(brief + section(CURSOR, "clean"), SAW) == ""


def test_the_round_verdict_is_the_worst_of_its_sections_whichever_wrote_last():
    found = section(CURSOR, "findings", findings=["warning a.py:1 a made up one"])
    for brief in (
        RESULT + TWO + section(CODEX, "clean") + found,
        RESULT + TWO + found + section(CODEX, "clean"),
    ):
        said = ready.said_of(brief)
        assert said.verdict == "findings"
        assert said.found == 1
        assert ready.short_of(brief, SAW) == ready.NO_FIXED
        handled = brief + "Finding: fixed, a made up one\nFixed: " + FIX + "\n"
        assert ready.short_of(handled, FIX) == ""


def test_a_section_that_was_not_run_outranks_findings_and_holds_the_merge():
    brief = RESULT + TWO + section(CODEX, "findings", findings=["error a.py:1 x"])
    brief += section(CURSOR, "not run")
    assert ready.said_of(brief).verdict not in ("clean", "findings")
    assert ready.short_of(brief, SAW) == ready.NO_VERDICT


def test_a_round_counts_once_so_a_later_clean_pass_still_reads_as_after_the_fix():
    """Two sections at one head are one round: `ran` counts rounds, and a clean scoped pass
    of the fix is the review that covers it, as with one reviewer."""
    first = section(CODEX, "findings", findings=["error a.py:1 x"]) + section(CURSOR, "clean")
    owed = f"Scoped review: needed since {SAW}, the fix changed a.py\n"
    brief = RESULT + TWO + "Finding: fixed, x\n" + owed + f"Fixed: {FIX}\n" + first
    assert ready.said_of(brief).ran == 1
    assert ready.short_of(brief, FIX) == ready.FIX_UNREVIEWED
    scoped = brief + section(CODEX, "clean", head=FIX)
    assert ready.said_of(scoped).ran == 2
    assert ready.short_of(scoped, FIX) == ""


def test_a_reviewer_whose_section_names_a_later_head_still_counts_as_written():
    """The reviewers are told apart by their `By:` lines, not by the head they saw."""
    brief = RESULT + TWO + section(CODEX, "clean") + section(CURSOR, "clean", head=FIX)
    assert ready.short_of(brief, FIX) == ""


def test_one_reviewer_and_a_section_with_no_by_line_read_as_before():
    brief = RESULT + "Reviewer: mcp:9\n" + "\n## Review\nVerdict: clean\nHead: " + SAW + "\n"
    assert ready.short_of(brief, SAW) == ""
    assert ready.said_of(brief).ran == 1
