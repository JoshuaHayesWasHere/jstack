"""jbus wakes a thread that waits on a full test slot when one is free (`jbus.slotwait.wake`). It
wakes the oldest waiter, once for each free slot, and once for each wait. Like
`test_jbus_kitchen.py`, the tests run the real pass against the fakes, with slots that are lock
files in a directory of the kitchen's own."""

import fcntl
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
from jbus import outbox
from jgauge import holders, slot, waiters
from jroles import waits
from test_jbus_kitchen import NOW, iso, sends

LANES = {"short": slot.short(), "full": slot.full(2)}
MIN = timedelta(minutes=1)


class Slots:
    """`Slots` is the lock files of the kitchen's slots, and `hold` takes them as a running test
    would."""

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


def waiter(kitchen, kind="full", ago=0, status="completed", **more):
    """Make a thread that ended its turn to wait on a slot, and register its wait `ago` minutes
    before NOW."""
    thread = kitchen.t3.thread("waiter", status, idle=timedelta(minutes=2), **more)
    lane = LANES[kind]
    command = ["uv", "run", "pytest", thread["threadId"]]
    at = NOW - timedelta(minutes=ago)
    waiters.register(slot.locks_dir(), thread["threadId"], kind, lane.slots, command, at)
    return thread["threadId"]


def told(kitchen):
    return [given["threadId"] for given in sends(kitchen)]


def test_two_waiters_one_slot_frees_only_the_oldest_is_woken(kitchen, slots):
    slots.hold("full")
    younger, older = waiter(kitchen, ago=3), waiter(kitchen, ago=9)
    kitchen.poll()
    assert sends(kitchen) == []
    slots.free("full")
    said = kitchen.poll()
    assert told(kitchen) == [older]
    (given,) = sends(kitchen)
    assert given["mode"] == "queue" and given["clientRequestId"].startswith(f"slot-wake|{older}|")
    assert "a full test slot is free" in given["message"]
    assert f"uv run pytest {older}" in given["message"]
    assert given["message"].endswith(jbus.END_TURN)
    line = f"slot-wake: woke {older}, a full slot is free for `uv run pytest {older}`, after 9 min"
    assert line in said and kitchen.lines("slot-wake") == [line]
    by = {one.thread: one for one in waiters.read(slot.locks_dir())}
    assert by[older].woken and not by[younger].woken


def test_a_taker_that_comes_between_the_count_and_the_send_finds_the_slot_claimed(
    kitchen, slots, monkeypatch
):
    slots.hold("full", 2)
    woken = waiter(kitchen, ago=9)
    lane = LANES["full"]
    took = []
    sending = outbox.send

    def taker_first(*args, **kwargs):
        took.append(slot.take(lane, thread="mcp:taker", command=["uv", "run", "pytest"]))
        return sending(*args, **kwargs)

    monkeypatch.setattr(outbox, "send", taker_first)
    kitchen.poll(datetime.now(UTC))
    for got in took:
        if got is not None:
            os.close(got[0])
    assert told(kitchen) == [woken] and took == [None]
    monkeypatch.setattr(outbox, "send", sending)
    held = slot.take(lane, thread=woken, command=["uv", "run", "pytest"])
    assert held is not None
    os.close(held[0])


def test_a_second_pass_wakes_no_one_twice(kitchen, slots):
    slots.hold("full")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    slots.free("full")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    kitchen.poll(NOW + timedelta(minutes=2))
    assert told(kitchen) == [first]
    assert [one.thread for one in waiters.read(slot.locks_dir()) if not one.woken] == [second]


def test_a_second_free_slot_wakes_the_next_waiter(kitchen, slots):
    slots.hold("full")
    first, second, third = waiter(kitchen, ago=9), waiter(kitchen, ago=6), waiter(kitchen, ago=3)
    slots.free("full", 1)
    kitchen.poll()
    slots.free("full", 2)
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [first, second]
    assert third not in told(kitchen)


def test_two_free_slots_wake_two_waiters_in_one_pass(kitchen, slots):
    slots.hold("full")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=6)
    third = waiter(kitchen, ago=3)
    slots.free("full", 1)
    slots.free("full", 2)
    kitchen.poll()
    assert told(kitchen) == [first, second] and third not in told(kitchen)


def test_a_waiter_that_was_woken_and_took_no_slot_holds_it_for_a_while(kitchen, slots):
    slots.hold("full", 2)
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    kitchen.poll()
    assert told(kitchen) == [first]
    kitchen.poll(NOW + waiters.HOLDS + timedelta(minutes=1))
    assert told(kitchen) == [first, second]


def test_a_waiter_that_waits_again_after_its_wake_is_woken_again_in_its_place(kitchen, slots):
    slots.hold("full")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    slots.free("full")
    kitchen.poll()
    slots.hold("full", 1)
    (was,) = [one for one in waiters.read(slot.locks_dir()) if one.thread == first]
    lane = LANES["full"].slots
    again = waiters.register(slot.locks_dir(), first, "full", lane, ["uv", "run", "pytest"], NOW)
    assert again.since == was.since and again.id != was.id and not again.woken
    slots.free("full")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [first, first]
    ids = {given["clientRequestId"] for given in sends(kitchen)}
    assert len(ids) == 2 and second not in told(kitchen)


@pytest.mark.parametrize(
    "how", ["gone", "settled", "archived", "failed", "interrupted", "cancelled"]
)
def test_a_dead_waiter_is_dropped_and_the_next_is_woken(kitchen, slots, how):
    slots.hold("full")
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
    slots.free("full")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [live]


def test_a_waiter_whose_thread_could_not_be_checked_is_kept(kitchen, slots):
    slots.hold("full")
    waiter(kitchen, ago=3)
    kitchen.t3.lose_read = True
    said = kitchen.poll()
    assert len(waiters.read(slot.locks_dir())) == 1
    assert any("could not be checked" in line for line in said)


def test_a_waiter_woken_long_ago_with_nothing_come_of_it_is_dropped(kitchen, slots):
    slots.hold("full")
    thread = waiter(kitchen, ago=9)
    slots.free("full")
    kitchen.poll()
    assert told(kitchen) == [thread]
    kitchen.poll(NOW + waiters.FORGOTTEN + timedelta(minutes=1))
    assert waiters.read(slot.locks_dir()) == [] and told(kitchen) == [thread]


def test_only_a_full_lane_waiter_is_woken_and_a_short_one_is_dropped_with_one_line(kitchen, slots):
    """A short call waits in its call and registers nothing, so a short-lane waiter in the file
    is one an older jgauge left: it gets no wake, whatever slot is free, and leaves the file."""
    slots.hold("short")
    slots.hold("full")
    short, full = waiter(kitchen, "short", ago=9), waiter(kitchen, "full", ago=3)
    slots.free("short")
    slots.free("full")
    said = kitchen.poll()
    assert told(kitchen) == [full]
    (line,) = about(said, short)
    assert "short" in line and "dropped" in line
    assert [one.thread for one in waiters.read(slot.locks_dir())] == [full]
    kitchen.poll(NOW + timedelta(minutes=1))
    assert told(kitchen) == [full]


@pytest.mark.parametrize("how", ["lose_send", "refuse_send"])
def test_a_lost_send_is_tried_again_with_the_same_key(kitchen, slots, how):
    slots.hold("full")
    thread = waiter(kitchen, ago=3)
    slots.free("full")
    setattr(kitchen.t3, how, True)
    said = kitchen.poll()
    assert any("could not be told a slot is free" in line for line in said)
    assert not waiters.read(slot.locks_dir())[0].woken
    setattr(kitchen.t3, how, False)
    kitchen.poll(NOW + timedelta(minutes=1))
    keys = {given["clientRequestId"] for given in sends(kitchen)}
    assert told(kitchen) == [thread, thread] and len(keys) == 1
    assert waiters.read(slot.locks_dir())[0].woken


def test_no_waiters_is_a_pass_that_sends_nothing(kitchen):
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("slot-wake") == []


def about(said, thread):
    return [line for line in said if thread in line]


def test_a_waiter_t3_code_no_longer_has_is_dropped_with_one_line(kitchen, slots):
    slots.hold("full")
    thread = waiter(kitchen, ago=3)
    kitchen.t3.threads.remove(next(t for t in kitchen.t3.threads if t["threadId"] == thread))
    (line,) = about(kitchen.poll(), thread)
    assert "is gone" in line and "no longer available" in line
    assert waiters.read(slot.locks_dir()) == []
    assert about(kitchen.poll(NOW + timedelta(minutes=1)), thread) == []


def test_a_waiter_t3_code_will_not_send_to_is_dropped_with_one_line(kitchen, slots):
    slots.hold("full")
    thread = waiter(kitchen, ago=3)
    slots.free("full")
    kitchen.t3.lose_read = True
    kitchen.t3.forgot.add(thread)
    said = kitchen.poll()
    (line,) = [line for line in about(said, thread) if "is gone" in line]
    assert "was not found" in line and not any("could not be told" in one for one in said)
    assert waiters.read(slot.locks_dir()) == [] and told(kitchen) == [thread]
    assert about(kitchen.poll(NOW + timedelta(minutes=1)), thread) == []
    assert told(kitchen) == [thread]


def turn(began, ended=None, status="completed"):
    """One of a thread's turns as T3 Code's read lists it, from `began` minutes before NOW to
    `ended` minutes before NOW, or still going with no `ended`."""
    return {
        "runId": f"run:{began}",
        "status": status,
        "requestedAt": iso(NOW - began * MIN),
        "startedAt": iso(NOW - began * MIN),
        "completedAt": None if ended is None else iso(NOW - ended * MIN),
    }


def ended_run(kitchen, status="completed", wrote=10, code=1, turns=()):
    """Make a thread whose own run under a full slot started 20 minutes before NOW and ended
    2 minutes before NOW with `code`, and that last wrote `wrote` minutes before NOW. Its turn
    that started the run ended 15 minutes before NOW unless `turns` says otherwise."""
    runs = list(turns) or [turn(21, 15)]
    thread = kitchen.t3.thread("holder", status, idle=timedelta(minutes=wrote), runs=runs)
    if status == "running":
        kitchen.t3.at_work.add(thread["threadId"])
    locks = slot.locks_dir()
    command = ["uv", "run", "pytest", "-n", "6"]
    run = holders.hold(locks, thread["threadId"], "full", os.getpid(), command, NOW - 20 * MIN)
    holders.end(locks, run.id, code, NOW - 2 * MIN)
    return thread["threadId"], run


def test_the_end_of_a_held_run_wakes_its_idle_thread_once(kitchen):
    thread, run = ended_run(kitchen)
    said = kitchen.poll()
    (given,) = sends(kitchen)
    assert given["threadId"] == thread and given["mode"] == "queue"
    assert given["clientRequestId"] == f"slot-end|{thread}|{run.since}"
    assert "`uv run pytest -n 6`" in given["message"] and "exit code 1" in given["message"]
    assert given["message"].endswith(jbus.END_TURN)
    assert any(line.startswith(f"slot-end: woke {thread}") for line in said)
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    assert told(kitchen) == [thread] and holders.read(slot.locks_dir()) == []


@pytest.mark.parametrize(
    ("status", "turns"),
    [
        ("running", [turn(21, 15), turn(5, status="running")]),
        ("completed", [turn(21, 1)]),
        ("running", [turn(21, status="running")]),
    ],
    ids=["at work", "its turn read the end", "its turn reads the end"],
)
def test_the_end_of_a_held_run_wakes_no_thread_at_work_or_one_whose_turn_got_the_end(
    kitchen, status, turns
):
    ended_run(kitchen, status, wrote=1, turns=turns)
    kitchen.poll()
    kitchen.poll(NOW + MIN)
    assert sends(kitchen) == []


def test_a_message_queued_after_the_run_ended_does_not_stand_for_reading_its_end(kitchen):
    """The run's own turn ended while it held the slot. A message queued after the run ended
    moved the thread's `updatedAt` and started a turn about something else: the thread is
    spared while that turn runs, and woken with the run's end once it is idle."""
    thread, run = ended_run(kitchen, "running", wrote=1, turns=[turn(21, 15), turn(1)])
    kitchen.t3.at_work.add(thread)
    kitchen.poll()
    assert sends(kitchen) == [] and len(holders.read(slot.locks_dir())) == 1
    (made,) = kitchen.t3.threads
    made["status"], made["runs"][-1] = "completed", turn(1, 0)
    kitchen.t3.at_work.discard(thread)
    kitchen.poll(NOW + MIN)
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"slot-end|{thread}|{run.since}"
    assert holders.read(slot.locks_dir()) == []


def test_a_run_still_held_wakes_nobody(kitchen):
    thread = kitchen.t3.thread("holder", "completed", idle=timedelta(minutes=10))
    command = ["make", "check"]
    holders.hold(slot.locks_dir(), thread["threadId"], "full", os.getpid(), command, NOW)
    kitchen.poll()
    assert sends(kitchen) == [] and len(holders.read(slot.locks_dir())) == 1


def test_a_run_whose_command_is_gone_and_whose_test_slot_lives_is_kept_until_its_end(kitchen):
    """ts-forget-unended, found by TLC on TestSlot.tla: the command ends, and before its `jgauge
    test-slot`, this process here, writes the end, jbus forgets the run. The end is then written
    to no entry, and the thread that ended its turn on its run holding a slot is never told."""
    thread = kitchen.t3.thread("holder", "completed", idle=timedelta(minutes=10))
    gone = subprocess.Popen(["true"])
    gone.wait()
    locks = slot.locks_dir()
    run = holders.hold(locks, thread["threadId"], "full", gone.pid, ["make", "check"], NOW)
    kitchen.poll()
    assert sends(kitchen) == [] and [one.id for one in holders.read(locks)] == [run.id]
    holders.end(locks, run.id, 1, NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"slot-end|{thread['threadId']}|{run.since}"
    assert "`make check`" in given["message"] and "exit code 1" in given["message"]


def test_an_ended_run_whose_wake_was_lost_is_sent_again_with_the_same_key(kitchen):
    thread, run = ended_run(kitchen)
    kitchen.t3.lose_send = True
    kitchen.poll()
    assert len(holders.read(slot.locks_dir())) == 1
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + MIN)
    keys = {given["clientRequestId"] for given in sends(kitchen)}
    assert keys == {f"slot-end|{thread}|{run.since}"} and holders.read(slot.locks_dir()) == []


def test_slot_wakes_run_once_a_pass(kitchen, slots):
    """The waiters and holders files belong to the machine, so a pass over three projects reads
    each waiter's thread and each thread with ended runs once, not once for each project and run
    (pass-slotwait-once, 2026-11-12: five project halves read them one after another, up to 12 s a
    pass), and still wakes each one as a pass over one project does."""
    kitchen.second("b")
    kitchen.second("c")
    slots.hold("full")
    first, second = waiter(kitchen, ago=9), waiter(kitchen, ago=3)
    busy, run = ended_run(kitchen, "running", wrote=1, turns=[turn(21, 15), turn(1)])
    again = holders.hold(
        slot.locks_dir(), busy, "full", os.getpid(), ["make", "check"], NOW - 9 * MIN
    )
    holders.end(slot.locks_dir(), again.id, 0, NOW - 3 * MIN)
    pooled = kitchen.t3.thread("waiter", "completed", idle=timedelta(minutes=2))["threadId"]
    waits.register(waits.where(), pooled, "review", NOW + 20 * MIN, NOW)

    def reads():
        asked = [given["threadId"] for tool, given in kitchen.t3.calls if tool == "t3_thread_read"]
        return {thread: asked.count(thread) for thread in (first, second, busy, pooled)}

    kitchen.poll()
    assert reads() == dict.fromkeys((first, second, busy, pooled), 1)
    assert sends(kitchen) == []
    slots.free("full")
    (made,) = [one for one in kitchen.t3.threads if one["threadId"] == busy]
    made["status"], made["runs"][-1] = "completed", turn(1, 0)
    kitchen.t3.at_work.discard(busy)
    kitchen.poll(NOW + MIN)
    keys = sorted(given["clientRequestId"].split("|")[:2] for given in sends(kitchen))
    assert keys == [["slot-end", busy], ["slot-wake", first]]
    kitchen.poll(NOW + 2 * MIN)
    ends = [given["clientRequestId"] for given in sends(kitchen)][1:]
    assert ends == [f"slot-end|{busy}|{run.since}", f"slot-end|{busy}|{again.since}"]
    assert holders.read(slot.locks_dir()) == []
