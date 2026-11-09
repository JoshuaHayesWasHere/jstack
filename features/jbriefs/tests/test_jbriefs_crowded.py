"""`jbus queue add` warns of a brief whose `Done when:` list has 5 or more items, and queues it
all the same (`jbriefs.crowded`, which `jbriefs.parse.warnings` prints). A brief that long took
a second review round about twice as often as one of 1 or 2 (po-briefs-scout, 2026-11-09), so
the line tells the home to split the row, and not to fold items into fewer lines, which keeps
the size and hides it."""

import pytest

from jbriefs import crowded, parse

BRIEF = (
    '# alpha: a task\nTask: "do alpha"\nDone when:\n{items}'
    "Proves it: `uv run pytest tests/test_alpha.py` passes\nSize: S\nWhere: `src/alpha/`\n"
    "Pull request: open one when done\nReview: review\nPlaybook: none\n"
)


def brief(count: int) -> str:
    items = "".join(
        f"- `uv run pytest tests/test_alpha.py::test_{n}` passes (in `src/alpha/a{n}.py`)\n"
        for n in range(1, count + 1)
    )
    return BRIEF.format(items=items)


def long_lines(text: str) -> list[str]:
    return [line for line in parse.warnings(text, "") if "Done when: lists" in line]


@pytest.mark.parametrize("count", [crowded.CROWDED, 7])
def test_a_brief_of_five_or_more_items_is_warned_to_split_and_still_queued(count):
    assert long_lines(brief(count)) == [
        f"brief's Done when: lists {count} items, and a brief of 5 or more took a second review "
        "round about twice as often as one of 1 or 2: split the row into briefs of one pull "
        'request\'s worth each, the rest on a brief with a "Follows: <slug>" line or queued with '
        "--depends, and do not fold items into fewer lines"
    ]
    assert parse.faults(brief(count)) == []


@pytest.mark.parametrize("count", [1, crowded.CROWDED - 1])
def test_a_brief_of_four_items_or_fewer_gets_no_such_line(count):
    assert long_lines(brief(count)) == []
    assert parse.warnings(brief(count), "") == []
