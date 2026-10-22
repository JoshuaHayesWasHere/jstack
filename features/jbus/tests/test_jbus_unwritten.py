"""A row whose thread ended, or hung, with nothing written is not left `stale` for nobody:
its home is told what to do, once, as a leftover's is, and the row drops out of `stale` when
it is handled. It waits on the user only where it has no home or the home did not close it.

Run as `features/jbus/tests/test_jbus_leftover.py` runs: the real pass, against a faked T3 Code server,
`gh` and `jmerge`, over briefs that are made up."""

from datetime import timedelta

import pytest

from jbus import leftover, watch
from jgauge import slot, waiters
from test_jbus_kitchen import NOW, iso
from test_jbus_leftover import home
from test_jbus_queue import add, rows
from test_jbus_row_ends import column, listed, result, sends
from test_jbus_slot_wake import Slots

MIN = timedelta(minutes=1)


@pytest.fixture
def slots(kitchen):
    made = Slots(slot.locks_dir())
    yield made
    made.close()


def lost(kitchen, status="completed", quiet=40):
    """A row jbus launched, whose thread went `status` `quiet` minutes ago with nothing
    written."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - 90 * MIN)
    (thread,) = kitchen.t3.threads
    thread |= {"status": status, "updatedAt": iso(NOW - quiet * MIN)}
    kitchen.t3.at_work.discard(thread["threadId"])
    return thread


def told(kitchen, at):
    return [given for given in sends(kitchen) if given["threadId"] == at]


def test_a_thread_that_ended_with_nothing_written_is_sent_to_its_home_once(kitchen):
    lost(kitchen)
    at = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "left"
    for minutes in (1, 2):
        kitchen.poll(NOW + minutes * MIN)
    (sent,) = told(kitchen, at)
    assert sent["clientRequestId"].startswith("leftover|alpha|") and sent["mode"] == "queue"
    said = sent["message"]
    assert said.startswith("jbus: alpha ended with nothing written")
    assert "its thread completed with nothing written" in said
    assert "`Status: done`" in said and "`Left: none`" in said
    assert "`jbus queue remove alpha --by" in said
    assert listed(kitchen) == []
    assert [row["status"] for row in rows(kitchen).values()] == ["left"]
    kitchen.poll(NOW + (leftover.CLOSE_MINUTES + 1) * MIN)
    (line,) = listed(kitchen)
    assert line.startswith("left alpha: its thread completed with nothing written; its home")
    assert len(told(kitchen, at)) == 1


def test_a_thread_that_hung_with_nothing_written_is_told_to_its_home_to_interrupt(kitchen):
    lost(kitchen, "running", quiet=25)
    at = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "left"
    (sent,) = told(kitchen, at)
    assert "its turn hung with nothing written" in sent["message"]
    assert "stopping its turn first" in sent["message"]


def test_a_thread_that_ended_a_moment_ago_is_still_its_crews_to_carry_on(kitchen):
    """The carry-on that jbus sends a crew whose thread ended is what handles it first."""
    thread = lost(kitchen, quiet=3)
    at = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "stale" and told(kitchen, at) == []
    thread["updatedAt"] = iso(NOW - 3 * MIN)
    kitchen.poll(NOW + 20 * MIN)
    assert column(kitchen)[0] == "left" and len(told(kitchen, at)) == 1


def test_a_row_drops_out_of_stale_when_its_home_writes_the_result_that_ends_it(kitchen):
    lost(kitchen)
    at = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert "alpha" in leftover.read(kitchen.state)
    with (kitchen.home / "tasks/alpha.md").open("a") as brief:
        brief.write(result().replace("## Result", "## Result, follow-up (2026-10-17, dropped)"))
    kitchen.poll(NOW + MIN)
    assert column(kitchen)[0] == "done" and listed(kitchen) == []
    assert "alpha" not in leftover.read(kitchen.state) and len(told(kitchen, at)) == 1


def test_a_row_drops_out_of_stale_when_its_thread_goes_on(kitchen):
    thread = lost(kitchen)
    home(kitchen)
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "left"
    thread |= {"status": "running", "updatedAt": iso(NOW + MIN)}
    kitchen.t3.at_work.add(thread["threadId"])
    kitchen.poll(NOW + MIN)
    assert column(kitchen)[0] == "running" and "alpha" not in leftover.read(kitchen.state)


def test_a_row_with_no_home_to_tell_waits_on_the_user_and_is_not_stale(kitchen):
    lost(kitchen)
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "left"
    (line,) = listed(kitchen)
    assert line.startswith("left alpha: its thread completed with nothing written")
    assert leftover.NO_HOME in line


def test_a_thread_that_waits_on_a_test_slot_is_not_left_however_long_it_is_quiet(kitchen, slots):
    slots.hold("full")
    thread = lost(kitchen, quiet=40)
    command = ["make", "check"]
    waiters.register(slot.locks_dir(), thread["threadId"], "full", 2, command, NOW - 40 * MIN)
    at = home(kitchen)["threadId"]
    for minutes in (0, 60, 180):
        kitchen.poll(NOW + minutes * MIN)
        assert column(kitchen)[0] == "stale"
    assert told(kitchen, at) == []


def test_a_waiter_still_silent_after_its_wake_is_left(kitchen, slots):
    slots.hold("full")
    thread = lost(kitchen, quiet=40)
    waiters.register(slot.locks_dir(), thread["threadId"], "full", 2, ["make", "check"], NOW)
    at = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert column(kitchen)[0] == "stale"
    slots.free("full")
    kitchen.poll(NOW + MIN)
    (woken,) = waiters.read(slot.locks_dir())
    assert woken.woken
    thread["updatedAt"] = iso(NOW + MIN)
    kitchen.poll(NOW + 5 * MIN)
    assert column(kitchen)[0] == "stale" and told(kitchen, at) == []
    kitchen.poll(NOW + (watch.UNWRITTEN_MINUTES + 2) * MIN)
    assert column(kitchen)[0] == "left" and len(told(kitchen, at)) == 1
