"""The crew's rebase waits while a review of its head is running: `reviewing()`, in the blocks
of "A link that moved" and "A conflict". It counts reviewers as `jmerge` does: once a
`Reviewer:` line carries its number, the numbered seats and their sections alone. Run as an
agent runs it, over briefs as the skills write them."""

import re
import subprocess

import pytest

from test_home_thread import blocks

SAW = "a" * 40
CODEX, CURSOR = "codex gpt-6-sol xhigh", "cursor grok-4.7 xhigh"
SONNET = "claudeAgent claude-sonnet-5-5 high"
TWO = "Reviewer: mcp:codex-1\nReviewer: mcp:cursor-2\n"
SEATS = "Reviewer: mcp:sonnet-a #1\nReviewer: mcp:sonnet-b #2\n"
RESULT = "# alpha\n\n## Result\nStatus: done\n"


def section(by):
    return f"\n## Review\nBy: {by}\nVerdict: clean\nHead: {SAW}\n"


def functions():
    """Each copy of `reviewing()` the crew skill gives, as an agent reads it."""
    found = [
        match[0]
        for block in blocks("crew")
        for match in re.finditer(r"^reviewing\(\) \{\n.*?^\}\n", block, re.M | re.S)
    ]
    assert len(found) == 2, "reviewing() is in the blocks of A link that moved and A conflict"
    return found


@pytest.fixture(params=range(2))
def reviewing(request, tmp_path):
    function = functions()[request.param]

    def run(brief):
        path = tmp_path / "brief.md"
        path.write_text(brief)
        script = f'B="{path}"\n{function}if reviewing; then echo running; else echo idle; fi\n'
        return subprocess.run(["sh", "-c", script], capture_output=True, text=True).stdout.strip()

    return run


def test_the_copies_are_one_rule():
    first, second = functions()
    assert first == second


def test_two_reviewers_one_written_is_a_review_running_and_both_is_none(reviewing):
    assert reviewing(RESULT + TWO + section(CODEX)) == "running"
    assert reviewing(RESULT + TWO + section(CODEX) + section(CURSOR)) == "idle"


def test_a_stalled_review_run_again_on_numbered_seats_waits_on_those_alone(reviewing):
    """The Codex reviewer that never wrote is a launch the numbered ones replaced: the rebase
    waits for #2 and not for it, and the old Cursor section fills no seat."""
    stalled = RESULT + TWO + section(CURSOR) + SEATS
    assert reviewing(stalled) == "running"
    assert reviewing(stalled + section(f"{SONNET} #1")) == "running"
    assert reviewing(stalled + section(f"{SONNET} #1") + section(f"{SONNET} #2")) == "idle"


def test_a_seat_launched_again_waits_for_no_more_sections(reviewing):
    brief = RESULT + SEATS + "Reviewer: mcp:sonnet-c #2\n"
    assert reviewing(brief + section(f"{SONNET} #1") + section(f"{SONNET} #2")) == "idle"


def test_a_scoped_reviewer_is_waited_on_beside_the_seats(reviewing):
    both = RESULT + SEATS + section(f"{SONNET} #1") + section(f"{SONNET} #2")
    scoped = both + f"Scoped reviewer: mcp:s-3, of {SAW}\n"
    assert reviewing(scoped) == "running"
    assert reviewing(scoped + section(f"{SONNET} #1")) == "idle"


def test_a_seat_that_wrote_twice_does_not_stand_for_a_seat_that_has_not(reviewing):
    """Review 1 of #166: two sections of #1 and none of #2 is a review still running."""
    brief = RESULT + SEATS + section(f"{SONNET} #1") + section(f"{SONNET} #1")
    assert reviewing(brief) == "running"
    assert reviewing(brief + section(f"{SONNET} #2")) == "idle"
