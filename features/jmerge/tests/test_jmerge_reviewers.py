"""A brief whose role map lists two reviewers gets a `## Review` section from each, both
written at the same head, and `jmerge` reads them as one round. The round waits for every
reviewer that the `Reviewer:` lines name, and its verdict is the worst of its sections. The
tests run through `ready.short_of`, the reader that the merge goes by, over briefs as the
skills write them."""

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
    """Two sections at one head are one round, because `ran` counts rounds. A clean scoped
    pass of the fix is the review that covers it, as with one reviewer."""
    first = section(CODEX, "findings", findings=["error a.py:1 x"]) + section(CURSOR, "clean")
    owed = f"Scoped review: needed since {SAW}, the fix changed a.py\n"
    brief = RESULT + TWO + "Finding: fixed, x\n" + owed + f"Fixed: {FIX}\n" + first
    assert ready.said_of(brief).ran == 1
    assert ready.short_of(brief, FIX) == ready.FIX_UNREVIEWED
    scoped = brief + section(CODEX, "clean", head=FIX)
    assert ready.said_of(scoped).ran == 2
    assert ready.short_of(scoped, FIX) == ""


def test_a_reviewer_whose_section_names_a_later_head_still_counts_as_written():
    """`jmerge` tells the reviewers apart by their `By:` lines, not by the head they saw."""
    brief = RESULT + TWO + section(CODEX, "clean") + section(CURSOR, "clean", head=FIX)
    assert ready.short_of(brief, FIX) == ""


def test_one_reviewer_and_a_section_with_no_by_line_read_as_before():
    brief = RESULT + "Reviewer: mcp:9\n" + "\n## Review\nVerdict: clean\nHead: " + SAW + "\n"
    assert ready.short_of(brief, SAW) == ""
    assert ready.said_of(brief).ran == 1


def test_a_reviewer_run_again_at_one_head_replaces_its_own_earlier_section():
    """A section that did not run, followed by the same reviewer's clean re-run at the same
    head, is a clean review. Within a round, each reviewer's last section is the one that
    counts."""
    one = RESULT + "Reviewer: mcp:9\n" + "\n## Review\nVerdict: not run\nHead: " + SAW + "\n"
    again = one + "\n## Review\nVerdict: clean\nHead: " + SAW + "\n"
    assert ready.short_of(one, SAW) == ready.NO_VERDICT
    assert ready.said_of(again).verdict == "clean"
    assert ready.short_of(again, SAW) == ""
    pair = RESULT + TWO + section(CODEX, "not run") + section(CURSOR, "clean")
    assert ready.short_of(pair, SAW) == ready.NO_VERDICT
    assert ready.short_of(pair + section(CODEX, "clean"), SAW) == ""


SONNET = "claudeAgent claude-sonnet-5-5 high"
SEATS = "Reviewer: mcp:sonnet-a #1\nReviewer: mcp:sonnet-b #2\n"


def test_two_reviewers_of_one_model_are_two_reviewers_by_their_numbers():
    """Two Sonnet reviewers write the same model and effort, so the number tells them apart.
    A brief with only one numbered review waits, and a brief with both numbered reviews
    passes. Question 38 records that `jmerge` once read two Cursor reviews as one."""
    one = RESULT + SEATS + section(f"{SONNET} #1", "clean")
    assert ready.short_of(one, SAW) == ready.NO_VERDICT
    both = one + section(f"{SONNET} #2", "clean")
    assert ready.short_of(both, SAW) == ""
    assert ready.said_of(both).verdict == "clean"


def test_a_numbered_review_does_not_take_the_place_of_the_other_numbers():
    found = section(f"{SONNET} #2", "findings", findings=["warning a.py:1 a made up one"])
    brief = RESULT + SEATS + section(f"{SONNET} #1", "clean") + found
    assert ready.said_of(brief).verdict == "findings"
    assert ready.short_of(brief, SAW) == ready.NO_FIXED


def test_a_seat_launched_again_does_not_double_the_count():
    brief = RESULT + SEATS + "Reviewer: mcp:sonnet-c #2\n"
    brief += section(f"{SONNET} #1", "clean") + section(f"{SONNET} #2", "clean")
    assert ready.short_of(brief, SAW) == ""


STALLED = RESULT + TWO + section(CURSOR, "findings", findings=["warning a.py:1 a made up one"])
STALLED += "Finding F1: fixed, a made up one\nFixed: none needed, it was answered\n"


def test_a_stalled_review_run_again_on_numbered_lines_reaches_a_verdict():
    """A brief whose Codex reviewer never wrote waits forever on its two unnumbered lines.
    Once the review runs again on two numbered lines, the brief waits for those two and no
    longer for the Codex one."""
    assert ready.short_of(STALLED, SAW) == ready.NO_VERDICT
    rerun = STALLED + SEATS + section(f"{SONNET} #1", "clean")
    assert ready.short_of(rerun, SAW) == ready.NO_VERDICT
    done = rerun + section(f"{SONNET} #2", "clean")
    assert ready.said_of(done).verdict == "clean"
    assert ready.short_of(done, SAW) == ""


def test_an_old_section_that_was_not_run_does_not_hold_a_numbered_round():
    brief = RESULT + TWO + section(CODEX, "not run") + SEATS
    brief += section(f"{SONNET} #1", "clean") + section(f"{SONNET} #2", "clean")
    assert ready.short_of(brief, SAW) == ""


def test_an_old_finding_still_needs_its_answer_after_a_numbered_round():
    brief = RESULT + TWO + section(CURSOR, "findings", findings=["error a.py:1 a made up one"])
    brief += SEATS + section(f"{SONNET} #1", "clean") + section(f"{SONNET} #2", "clean")
    assert ready.short_of(brief, SAW) != ""
    answered = brief + "Finding F1: fixed, a made up one\n"
    assert ready.short_of(answered, SAW) == ""


def test_a_scoped_pass_numbered_one_does_not_take_the_place_of_reviewer_one():
    first = section(f"{SONNET} #1", "findings", findings=["error a.py:1 x"])
    first += section(f"{SONNET} #2", "clean")
    owed = f"Scoped review: needed since {SAW}, the fix changed a.py\n"
    brief = RESULT + SEATS + "Finding F1: fixed, x\n" + owed + f"Fixed: {FIX}\n" + first
    assert ready.short_of(brief, FIX) == ready.FIX_UNREVIEWED
    scoped = brief + section(f"{SONNET} #1", "clean", head=FIX).replace("By:", "Scope: a.py\nBy:")
    assert ready.said_of(scoped).ran == 2
    assert ready.short_of(scoped, FIX) == ""
