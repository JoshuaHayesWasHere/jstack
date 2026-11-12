"""jbus launches a review at the head of a brief's last `Checked:` line (`jbus.review.desk_head`),
and jmerge binds a merge to that line (`ready.short_on_checked`): both read it through
`jbriefs.checked`, so the review and the merge name one head.

The line here is fl-browser-red-holds's, a real brief whose last line has a note after its head:
jbus read the note's commit, 04d7539a, and jmerge the line before, 530519cd."""

from jbus import review
from jmerge import ready

BEFORE = "530519cd2c0e540fa6c3fb5fee0152def6247ca0"
NOTE = "04d7539a11dcba48fd99e5e8e7b8b70304530b44"
BASE = "b" * 40
BRIEF = f"""\
# fl-browser-red-holds: a task

## Result
Status: done
Checked: make check-fast BASE={BASE} PART=touched exit 0 at {BEFORE}

## Result, follow-up (2026-10-27, the review's findings)
Status: done
Checked: make check-fast BASE={BASE} PART=touched exit 0 at {"a" * 40}, and after merging \
the branch's merge of main the guards and feature tests passed (117) at {NOTE}
"""


def test_jbus_and_jmerge_read_the_same_checked_line_and_the_same_head():
    head = review.desk_head(BRIEF)
    assert head == BEFORE
    assert ready.short_on_checked(BRIEF, head) == ""
    assert ready.short_on_checked(BRIEF, NOTE) != ""


def test_a_brief_with_no_checked_line_in_its_shape_has_no_desk_head_and_no_binding():
    brief = BRIEF.replace(f"exit 0 at {BEFORE}", "exit 0")
    assert review.desk_head(brief) == ""
    assert ready.short_on_checked(brief, BEFORE) == ready.CHECKED_MISSING.format(head=BEFORE[:12])
