"""A launched row whose thread left T3 Code's list with nothing written does not wait at
`launched` for good. Its row is `stale`, and the pass sends it home as `left`, with the why of a
gone thread (`watch.unwritten`), whether T3 Code no longer has the thread (`Thread.MISSING`) or
still has it but lists it under no row (`Thread.NONE`, `watch.gone`).

Like `test_jbus_unwritten.py`, the tests run the real pass against a faked T3 Code server, `gh`
and `jmerge`, over briefs that are made up."""

from datetime import timedelta

import pytest

from jbus import leftover, watch
from test_jbus_kitchen import NOW
from test_jbus_leftover import home
from test_jbus_queue import add
from test_jbus_row_ends import column, sends

MIN = timedelta(minutes=1)
WHY = "its thread is gone and nothing is written"


def deleted(kitchen, thread):
    """T3 Code no longer has the thread: a read of it says so (`World.missing`)."""
    kitchen.t3.threads.remove(thread)


def unlisted(kitchen, thread):
    """T3 Code still has the thread, unarchived, but its list names it under no row."""
    thread["title"] = "crew: someone-else"


@pytest.mark.parametrize("leave", [deleted, unlisted])
def test_a_launched_row_whose_thread_left_t3_codes_list_goes_home_as_left(kitchen, leave):
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - 90 * MIN)
    (thread,) = kitchen.t3.threads
    at = home(kitchen)["threadId"]
    leave(kitchen, thread)
    kitchen.poll(NOW + (watch.UNWRITTEN_MINUTES + 1) * MIN)
    assert column(kitchen) == ("left", "", WHY)
    assert "alpha" in leftover.read(kitchen.state)
    told = [one for one in sends(kitchen) if one["threadId"] == at]
    assert any(WHY in one["message"] for one in told)
