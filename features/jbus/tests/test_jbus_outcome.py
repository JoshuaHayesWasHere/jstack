"""A brief's last Result names how its row ended with no merge (`jbus.outcome.read`): carried by
another row, nothing to change, or dropped. A brief that asks for no pull request owes no line."""

import pytest

from jbus import outcome
from jbus.outcome import CarriedBy, Dropped, NoPullOwed, NothingToChange

OPENS = "# alpha: a task\nPull request: open one when done\n"


def closed(*lines, head=OPENS):
    body = "".join(f"{one}\n" for one in lines)
    result = "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\n"
    return f"{head}{result}{body}Left: none\n"


@pytest.mark.parametrize(
    ("line", "read"),
    [
        ("Outcome: carried by alpha-2", CarriedBy("alpha-2")),
        ("Outcome: carried by `alpha-2`.", CarriedBy("alpha-2")),
        ("Outcome: nothing to change, main does it", NothingToChange("main does it")),
        ("Outcome: dropped, the user no longer wants it", Dropped("the user no longer wants it")),
        ("Outcome: dropped", None),
        ("Outcome: finished somehow", None),
        ("", None),
    ],
)
def test_a_close_with_no_merge_reads_as_the_outcome_its_line_names(line, read):
    assert outcome.read(closed(line) if line else closed()) == read


@pytest.mark.parametrize("asks", ["Pull request: none\n", "Pull request: ask first\n", ""])
def test_a_brief_that_asks_for_no_pull_request_owes_no_line(asks):
    assert outcome.read(closed(head=f"# alpha: a task\n{asks}")) == NoPullOwed()


def test_only_the_last_result_and_its_own_lines_name_the_outcome():
    first = closed("Outcome: dropped, an early guess")
    later = "\n## Result, follow-up (2026-11-10, carried)\nStatus: done\nLeft: none\n"
    review = "\n## Review\nOutcome: carried by alpha-2\n"
    assert outcome.read(first + later + review) is None
    assert outcome.read(first + review) == Dropped("an early guess")


@pytest.mark.parametrize(
    ("ended", "word"),
    [
        (CarriedBy("alpha-2"), "carried"),
        (NothingToChange("main does it"), "nothing to change"),
        (Dropped("unwanted"), "dropped"),
        (NoPullOwed(), None),
        (None, None),
    ],
)
def test_the_store_keeps_the_end_a_close_names_and_nothing_for_none(ended, word):
    """`brief-versions.jsonl` keeps the word `row_outcomes` names the row's end by; the version's
    `pull` already says that a row owed no merge."""
    assert outcome.kind(ended) == word
