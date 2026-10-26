"""A row whose thread ended, or hung, with nothing written does not stay `stale` with nobody to
handle it. jbus tells its home what to do, once, as it does for a leftover, and the row drops out
of `stale` when the home handles it. The row waits on the user only where it has no home or the
home did not close it.

Like `test_jbus_leftover.py`, the tests run the real pass against a faked T3 Code server, `gh`
and `jmerge`, over briefs that are made up."""

from datetime import timedelta

import pytest

from jbus import leftover, watch
from jgauge import slot, waiters
from test_jbus_kitchen import NOW, iso
from test_jbus_leftover import home
from test_jbus_live import written
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
    """Make a row that jbus launched, whose thread took the status `status` `quiet` minutes ago
    and wrote nothing."""
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
    """When a crew's thread ends, jbus handles the row first by sending the crew a carry-on."""
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


@pytest.mark.parametrize("approval", [True, False], ids=["an approval", "no approval"])
def test_a_crew_whose_approval_was_just_answered_is_not_hung_on_the_silence_it_left(
    kitchen, approval
):
    """The crew hometree-today, 2026-10-25: its last item at 20:22Z, an approval that waited from
    20:22Z to 20:39Z, and nothing written until 20:45Z. T3 Code counts the requests that wait and
    keeps no time for the answer, and the answer writes no item. So the pass that sees the count
    fall to 0 counts that as the thread's last write. Without the approval, the same silence is a
    hang at 20 minutes, at the 20:42Z pass."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - 30 * MIN)
    (thread,) = kitchen.t3.threads
    thread |= {"status": "running", "updatedAt": iso(NOW), "itemCount": 40}
    kitchen.t3.at_work.discard(thread["threadId"])
    at = home(kitchen)["threadId"]
    words = {}
    for minute in range(1, 24):
        if approval:
            thread["pendingRequestCount"] = 1 if minute <= 17 else 0
        kitchen.poll(NOW + minute * MIN)
        (found,) = [one for one in written(kitchen) if one["id"] == thread["threadId"]]
        words[minute] = found["live"]
    hung = kitchen.state / "hung.jsonl"
    if approval:
        assert "hung" not in words.values(), words
        assert told(kitchen, at) == [] and not hung.exists()
    else:
        assert [minute for minute, word in words.items() if word == "hung"][0] == 20
        assert "its turn hung with nothing written" in told(kitchen, at)[0]["message"]


@pytest.mark.parametrize("gap", ["missing", "None", "a string", "a failed read"])
def test_a_read_with_no_request_count_keeps_the_count_until_one_reads_0(kitchen, gap):
    """The same approval, with a pass between the 1 and the 0 whose read gives no int
    `pendingRequestCount`, or fails. That pass keeps the 1 the pass before kept and does not
    restart the silence, and the next pass, which reads 0, counts the answer as the last write."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - 30 * MIN)
    (thread,) = kitchen.t3.threads
    thread |= {"status": "running", "updatedAt": iso(NOW), "itemCount": 40}
    kitchen.t3.at_work.discard(thread["threadId"])
    at = home(kitchen)["threadId"]
    found = {}
    for minute in range(1, 24):
        thread["pendingRequestCount"] = 1 if minute <= 17 else 0
        kitchen.t3.lose_read = minute == 18 and gap == "a failed read"
        if minute == 18 and gap == "missing":
            del thread["pendingRequestCount"]
        elif minute == 18 and gap != "a failed read":
            thread["pendingRequestCount"] = {"None": None, "a string": "0"}[gap]
        said = kitchen.poll(NOW + minute * MIN)
        if minute == 18 and gap == "a failed read":
            assert any(line.startswith("wait alpha: its thread could not be read") for line in said)
        (found[minute],) = [one for one in written(kitchen) if one["id"] == thread["threadId"]]
    assert (found[18]["pending"], found[18]["silent"]) == (1, 18), found[18]
    assert (found[19]["pending"], found[19]["silent"]) == (0, 0), found[19]
    assert "hung" not in [one["live"] for one in found.values()]
    assert told(kitchen, at) == [] and not (kitchen.state / "hung.jsonl").exists()
