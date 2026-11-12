"""A row's go given back by the queue's own verbs: a lift puts back the go a hold kept
(`queue.hold` with `keep`, `queue.lift`). The entry pass and a gate's default have their own
tests, in `test_jbus_entrygo.py`. Like `test_jbus_queue.py`, the test runs the real queue
against the kitchen's fakes, and reads what the row holds afterwards."""

import pytest

from jbus import queue
from test_jbus_queue import add, kitchen, rows, widened

__all__ = ["kitchen"]


GO_COLUMNS = ("approved", "approval", "brief_sha")


def test_a_lift_puts_back_the_go_a_hold_kept_and_a_changed_brief_stays_held(kitchen):
    """A hold that keeps its go (`queue.hold` with `keep`), as `jbus.stall.twice` holds a row
    whose check failed twice, is ended by `queue.lift`, which puts that go back as it was. A
    row whose brief changed since that go stays held: the go was for another brief."""
    add(kitchen, "alpha")
    had = {column: rows(kitchen)["alpha"][column] for column in GO_COLUMNS}
    assert had["approved"]
    queue.hold(kitchen.state, "alpha", keep=True)
    assert rows(kitchen)["alpha"]["held"] and not rows(kitchen)["alpha"]["approved"]
    said = queue.lift(kitchen.state, "alpha")
    assert said == f"lifted alpha's hold, and its go is back: {had['approved']}"
    row = rows(kitchen)["alpha"]
    assert {column: row[column] for column in GO_COLUMNS} == had
    assert "held" not in row and "hold" not in row
    queue.hold(kitchen.state, "alpha", keep=True)
    add(kitchen, "alpha", approve=False, text=widened("alpha"))
    with pytest.raises(queue.Refused, match="alpha's brief changed since the go its hold took"):
        queue.lift(kitchen.state, "alpha")
    row = rows(kitchen)["alpha"]
    assert row["held"] and not row["approved"] and "approval" not in row
