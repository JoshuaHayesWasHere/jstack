"""A thread that waits on a test slot is woken when a slot of its lane is free: the oldest
waiter, once for each free slot, and once for each wait. Run as `test_jbus_kitchen.py`
runs: the real pass, against the fakes, and slots that are lock files in a directory of the
kitchen's own."""

import fcntl
import os
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jgauge import slot, waiters
from test_jbus_kitchen import NOW, sends

LANES = {"short": slot.short(), "full": slot.full(2)}


class Slots:
    """The lock files of the kitchen's slots: `hold` takes them as a running test would."""

    def __init__(self, locks):
        self.locks, self.fds = Path(locks), {}

    def hold(self, kind, *numbers):
        lane = LANES[kind]
        self.locks.mkdir(parents=True, exist_ok=True)
        for n in numbers or range(1, lane.slots + 1):
            fd = os.open(self.locks / f"{lane.lock}.{n}.lock", os.O_RDWR | os.O_CREAT)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fds[kind, n] = fd

    def free(self, kind, n=1):
        os.close(self.fds.pop((kind, n)))

    def close(self):
        for fd in self.fds.values():
            os.close(fd)


@pytest.fixture
def slots(kitchen):
    made = Slots(slot.locks_dir())
    yield made
    made.close()


def waiter(kitchen, kind="short", ago=0, status="completed", **more):
    """A thread that ended its turn to wait on a slot, registered `ago` minutes before NOW."""
    thread = kitchen.t3.thread("waiter", status, idle=timedelta(minutes=2), **more)
    lane = LANES[kind]
    command = ["uv", "run", "pytest", thread["threadId"]]
    at = NOW - timedelta(minutes=ago)
    waiters.register(slot.locks_dir(), thread["threadId"], kind, lane.slots, command, at)
    return thread["threadId"]


def told(kitchen):
    return [given["threadId"] for given in sends(kitchen)]


def test_two_waiters_one_slot_frees_only_the_oldest_is_woken(kitchen, slots):
    slots.hold("short")
    younger, older = waiter(kitchen, ago=3), waiter(kitchen, ago=9)
    kitchen.poll()
    assert sends(kitchen) == []
    slots.free("short")
    said = kitchen.poll()
    assert told(kitchen) == [older]
    (given,) = sends(kitchen)
    assert given["mode"] == "queue" and given["clientRequestId"].startswith(f"slot-wake|{older}|")
    assert "a short test slot is free" in given["message"]
    assert f"uv run pytest {older}" in given["message"]
    assert given["message"].endswith(jbus.END_TURN)
    line = f"slot-wake: woke {older}, a short slot is free for `uv run pytest {older}`, after 9 min"
    assert line in said and kitchen.lines("slot-wake") == [line]
    by = {one.thread: one for one in waiters.read(slot.locks_dir())}
    assert by[older].woken and not by[younger].woken


def test_a_second_pass_wakes_no_one_twice(kitchen, slots):
    slots.hold("short")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    slots.free("short")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    kitchen.poll(NOW + timedelta(minutes=2))
    assert told(kitchen) == [first]
    assert [one.thread for one in waiters.read(slot.locks_dir()) if not one.woken] == [second]


def test_a_second_free_slot_wakes_the_next_waiter(kitchen, slots):
    slots.hold("short")
    first, second, third = waiter(kitchen, ago=9), waiter(kitchen, ago=6), waiter(kitchen, ago=3)
    slots.free("short", 1)
    kitchen.poll()
    slots.free("short", 2)
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [first, second]
    assert third not in told(kitchen)


def test_two_free_slots_wake_two_waiters_in_one_pass(kitchen, slots):
    slots.hold("short")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=6)
    third = waiter(kitchen, ago=3)
    slots.free("short", 1)
    slots.free("short", 2)
    kitchen.poll()
    assert told(kitchen) == [first, second] and third not in told(kitchen)


def test_a_waiter_that_was_woken_and_took_no_slot_holds_it_for_a_while(kitchen, slots):
    slots.hold("short", 2, 3)
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    kitchen.poll()
    assert told(kitchen) == [first]
    kitchen.poll(NOW + waiters.HOLDS + timedelta(minutes=1))
    assert told(kitchen) == [first, second]


def test_a_waiter_that_waits_again_after_its_wake_is_woken_again_in_its_place(kitchen, slots):
    slots.hold("short")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    slots.free("short")
    kitchen.poll()
    slots.hold("short", 1)
    (was,) = [one for one in waiters.read(slot.locks_dir()) if one.thread == first]
    again = waiters.register(slot.locks_dir(), first, "short", 3, ["uv", "run", "pytest"], NOW)
    assert again.since == was.since and again.id != was.id and not again.woken
    slots.free("short")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [first, first]
    ids = {given["clientRequestId"] for given in sends(kitchen)}
    assert len(ids) == 2 and second not in told(kitchen)


@pytest.mark.parametrize(
    "how", ["gone", "settled", "archived", "failed", "interrupted", "cancelled"]
)
def test_a_dead_waiter_is_dropped_and_the_next_is_woken(kitchen, slots, how):
    slots.hold("short")
    dead, live = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    thread = next(t for t in kitchen.t3.threads if t["threadId"] == dead)
    if how == "gone":
        kitchen.t3.threads.remove(thread)
    elif how in ("settled", "archived"):
        thread[how] = True
    else:
        thread["status"] = how
    kitchen.poll()
    assert [one.thread for one in waiters.read(slot.locks_dir())] == [live]
    assert sends(kitchen) == []
    slots.free("short")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [live]


def test_a_waiter_whose_thread_could_not_be_checked_is_kept(kitchen, slots):
    slots.hold("short")
    waiter(kitchen, ago=3)
    kitchen.t3.lose_read = True
    said = kitchen.poll()
    assert len(waiters.read(slot.locks_dir())) == 1
    assert any("could not be checked" in line for line in said)


def test_a_waiter_woken_long_ago_with_nothing_come_of_it_is_dropped(kitchen, slots):
    slots.hold("short")
    thread = waiter(kitchen, ago=9)
    slots.free("short")
    kitchen.poll()
    assert told(kitchen) == [thread]
    kitchen.poll(NOW + waiters.FORGOTTEN + timedelta(minutes=1))
    assert waiters.read(slot.locks_dir()) == [] and told(kitchen) == [thread]


def test_the_lanes_wake_their_own_waiters(kitchen, slots):
    slots.hold("short")
    slots.hold("full")
    short, full = waiter(kitchen, "short", ago=3), waiter(kitchen, "full", ago=9)
    slots.free("short")
    kitchen.poll()
    assert told(kitchen) == [short]
    slots.free("full")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [short, full]


def test_a_lost_send_is_tried_again_with_the_same_key(kitchen, slots):
    slots.hold("short")
    thread = waiter(kitchen, ago=3)
    slots.free("short")
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert any("could not be told a slot is free" in line for line in said)
    assert not waiters.read(slot.locks_dir())[0].woken
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + timedelta(minutes=1))
    keys = {given["clientRequestId"] for given in sends(kitchen)}
    assert told(kitchen) == [thread, thread] and len(keys) == 1
    assert waiters.read(slot.locks_dir())[0].woken


def test_no_waiters_is_a_pass_that_sends_nothing(kitchen):
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("slot-wake") == []
