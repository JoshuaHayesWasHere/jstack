"""A line `jmerge` wrote keeps its reason's code after the reason is reworded. `merge.log` and a
queue row's `why` hold the text as `jmerge` wrote it, and the view reads the code, and so the
step, from that text with today's `ready.rules`. #1715 reworded the desk check's words in five
`CHECKED_*` reasons, and every line of theirs written before it went to the view's Unknown lane.

`reason_wordings.txt` keeps every wording each `Reason` has had, one `NAME<tab>text` line each,
and only grows: a rewording appends its new text and keeps the old one, and the reason carries
the old text in its `earlier`, so a line in either wording gets the reason's code and step."""

import string
from pathlib import Path

from jmerge import ready

WORDINGS = Path(__file__).with_name("reason_wordings.txt")


def _wordings():
    return [tuple(line.split("\t")) for line in WORDINGS.read_text().splitlines()]


def _filled(template):
    names = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**dict.fromkeys(names, "x1"))


def test_a_line_in_any_wording_a_reason_has_had_gets_its_code_and_step():
    reasons = ready.reasons()
    read = {
        (name, text): (ready.code_of(_filled(text)), ready.step_of(ready.code_of(_filled(text))))
        for name, text in _wordings()
    }
    assert read == {
        (name, text): (reasons[name].code, reasons[name].step) for name, text in _wordings()
    }, "a reworded Reason keeps its old text in `earlier=`, so lines written in it keep its code"


def test_each_reason_has_its_text_of_today_among_its_wordings():
    """A new or reworded reason appends its text to the record, and a reworded one keeps the
    line of its old text, which the test above then holds it to."""
    kept = set(_wordings())
    assert [name for name, text in ready.reasons().items() if (name, str(text)) not in kept] == []


def test_the_desk_checks_words_from_before_1715_place_1718s_line_as_stale():
    """#1718's row, as jbus's view read it on 2026-11-11: the wait jmerge wrote before #1715."""
    line = (
        "its last Checked: line is of 2340e1f7de54, and its patch changed after it: the crew's "
        "check block (features/crew/do-the-task.md), which runs `make check-fast PART=touched`, "
        "the lint, the touched tests and the repo-guards tests, and writes its line (a "
        "`PART=guards` line of an earlier head binds too), runs again at ba66f41642f6"
    )
    assert (ready.code_of(line), ready.step_of(ready.code_of(line))) == ("checked-stale", "result")


def test_a_meets_no_wait_that_names_the_users_waived_line_keeps_its_code():
    """A meets-no wait written before the waiver was the root's to record, as jbus's view holds it
    in merge.log and a row's `why`: once the reason ends in "a Waived: line for those lines", the
    line still reads as `MEETS_NO`, `meets-no` on the findings step, not the view's Unknown lane."""
    for way_out in (
        "or the user's Waived: line",
        "or a waiver: the root home's jbus waive --as root, or the user's Waived: line",
    ):
        line = (
            "its review at 5d41402abc4b says the brief is not met, 2 of 3: Done when 2 unmet, so "
            f"a fix and a scoped review whose line says yes, {way_out}"
        )
        assert (ready.code_of(line), ready.step_of(ready.code_of(line))) == (
            "meets-no",
            "findings",
        ), line
