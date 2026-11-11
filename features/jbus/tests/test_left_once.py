"""A row whose pull request is opening is never written as left.

A crew whose Result opens its pull request after its review is on its way to that pull request
while the review is due or running, and once it is written while the crew opens it
(`leftover.opening`). The pass writes such a row's status as what its facts give, so no move to
`left` lands in `transitions.jsonl` for it and is taken back when the row is read. The tests run
the real pass against the kitchen's fakes, as `test_jbus_leftover.py` does."""

import pytest

from jbus import leftover
from test_jbus_leftover import WRITTEN, awaiting, home, later, lefts
from test_jbus_row_ends import column
from test_jbus_row_history import transitions


def moves(kitchen):
    return [(one["from"], one["to"]) for one in transitions(kitchen)]


@pytest.mark.parametrize("thread", ["completed", "running"])
def test_a_row_opening_its_pull_request_moves_to_pr_and_never_to_left(kitchen, thread):
    home(kitchen)
    awaiting(kitchen, WRITTEN, status=thread)
    for minutes in (0, leftover.OPENING_MINUTES - 1):
        kitchen.poll(later(minutes))
        assert column(kitchen)[0] == "running"
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll(later(leftover.OPENING_MINUTES))
    assert column(kitchen)[:2] == ("pr", "#7")
    assert moves(kitchen) == [("queued", "running"), ("running", "pr")]
    assert lefts(kitchen) == []


def test_a_row_whose_crew_opens_nothing_past_the_window_moves_to_left_once(kitchen):
    home(kitchen)
    awaiting(kitchen, WRITTEN)
    for minutes in (0, leftover.OPENING_MINUTES + 1, leftover.OPENING_MINUTES + 2):
        kitchen.poll(later(minutes))
    assert moves(kitchen) == [("queued", "running"), ("running", "left")]
    (sent,) = lefts(kitchen)
    assert "It ended with no pull request.\nLeft: the docs\n" in sent["message"]
