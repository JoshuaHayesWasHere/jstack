"""This module wakes a thread that waits on a test slot once a slot of its lane is free, and a
thread that waits on a capped pool once the cap has ended.

A thread that finds every slot taken registers in `test-slot-waiters.json` (`jgauge.waiters`,
which `jgauge test-slot --thread` writes) and ends its turn. Nothing in T3 Code resumes that
thread, so each pass of `jbus poll` resumes it, in `wake`:

- `wake` drops a waiter whose thread is gone, settled, archived or ended (`dead`). A thread
  that ended its turn to wait has the status `completed`, and counts as alive. A wait whose
  read or send T3 Code answers with a gone thread is dropped with one line, and not tried again.
- `wake` drops a woken waiter that jbus told long ago and that has done nothing since.
- For each lane that has a slot free, `wake` wakes the oldest waiters on it, one for each free
  slot that a woken waiter has not claimed already. A woken waiter claims its slot for
  `waiters.HOLDS`: jbus has told the waiter, and the waiter has not taken the slot yet.
- A wake is one queued message (`jbus.outbox.send`), keyed by the wait, so a retry sends the same
  message. jbus records the wait as woken only after T3 Code took the message. So jbus wakes
  each wait once, and sends again a message that got no answer.

A thread can also end its turn while its own run holds a slot. `jgauge test-slot --thread`
records the run in `test-slot-holders.json` (`jgauge.holders`), and its end and exit code once the
command ends. While the run holds its slot the thread is at work (`watch.World.holding`). Once the
run has ended, `wake_ended` sends the thread one message in mode queue that names the command and
its exit code, keyed by the thread and the run's start, so one run wakes once. It sends none to a
thread whose turn that started the run was still going when the run ended, which got the end
itself (`_got_end`), and none yet to a thread at work. A run that ended with no wake owed, or
whose holder died with no end recorded, leaves the file.

`test-slot-waiters.json` belongs to the machine, not to a project. A pass of any project wakes any
waiter, and once one pass records a wake in the file, the other passes read that record there. A
thread that takes a slot leaves the file (`jgauge.slot.take`).

A crew that finds every instance of the review pool capped registers in `pool-waiters.json`
(`jroles.waits`, which `jroles review --thread` writes) with the time the cap ends, and ends its
turn. `wake_capped` wakes it the same way: it drops a wait whose thread is `dead`, and once the
cap's end has passed it sends the thread one message in mode queue, keyed by the wait. The wait
leaves the file as soon as T3 Code took the message, and only then, so a send that got no answer
is sent again with the same key, and the thread's next wait has a key of its own.
"""

from __future__ import annotations

import shlex
from collections import defaultdict
from datetime import datetime
from typing import Any

from jbus import END_TURN, outbox, verbs
from jbus.passes import Pass
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.watch import ENDED, at_work, when
from jgauge import holders, slot, waiters
from jgauge.holders import Holder
from jgauge.waiters import Waiter
from jroles import waits
from jroles.waits import Wait

EVENTS = {"slot-wake": "quiet", "slot-end": "quiet", "pool-wake": "quiet"}
OVER = (*ENDED, "rolled_back")
RUNS = 20
MESSAGE = (
    "jbus: a {lane} test slot is free. Run again what you waited to run: `{command}`. If every"
    " slot is taken again by then, register again and end your turn: jbus wakes you once for"
    " each wait. " + END_TURN
)
ENDED_RUN = (
    "jbus: your run of `{command}` under a {lane} test slot has ended, with exit code {code}."
    " Read what it printed and go on with the task from there. " + END_TURN
)
CAPPED = (
    "jbus: the {role} pool was capped until {until}, and that time has passed. Run `jroles {role}"
    " --thread {thread}` again and make the launch you waited to make, as the crew skill's \"The"
    ' review" says. If the pool is capped again, that run registers you again: end your turn,'
    " and jbus wakes you once for each wait. " + END_TURN
)


def dead(run: Pass, client: Client, waiter: Waiter | Wait) -> bool:
    """Say whether the waiter's thread cannot be woken: it is gone, settled or archived, or it
    ended with a failure, an interrupt or a cancel. When T3 Code does not answer about the
    thread, `dead` returns False."""
    try:
        read = client.call("t3_thread_read", {"threadId": waiter.thread, "limit": 1})
    except T3Refused as error:
        if GONE.search(str(error)):
            return _gone(run, waiter, error)
        run.say(f"wait {waiter.thread}: its {_kind(waiter)} wait could not be checked ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {waiter.thread}: its {_kind(waiter)} wait could not be checked ({error})")
        return False
    thread: dict[str, Any] = read.get("thread") or {}
    return bool(thread.get("settled") or thread.get("archived")) or thread.get("status") in OVER


def _kind(waiter: Waiter | Wait) -> str:
    return "pool" if isinstance(waiter, Wait) else "slot"


def _gone(run: Pass, waiter: Waiter | Wait, error: T3Error) -> bool:
    run.say(
        f"wait {waiter.thread}: its {_kind(waiter)} wait is dropped, its thread is gone ({error})"
    )
    return True


def wake(run: Pass, client: Client) -> None:
    """Drop the waiters that cannot be woken, and wake the oldest ones for the free slots."""
    locks = slot.locks_dir()
    held = waiters.read(locks)
    if not held:
        return
    gone = {one.id for one in held if waiters.lapsed(one, run.now)}
    alive: list[Waiter] = []
    for one in held:
        if one.id in gone:
            continue
        if dead(run, client, one):
            gone.add(one.id)
        else:
            alive.append(one)
    if gone:
        waiters.forget(locks, gone)
    lanes: dict[tuple[str, int], list[Waiter]] = defaultdict(list)
    for one in alive:
        lanes[one.lane, one.slots].append(one)
    for (kind, slots), queue in sorted(lanes.items()):
        lane = slot.lane_of(kind, slots)
        claimed = sum(waiters.holding(one, run.now) for one in queue)
        room = slot.free(lane) - claimed
        waiting = [one for one in queue if not one.woken]
        for one in waiting[: max(room, 0)]:
            tell(run, client, one)


def wake_capped(run: Pass, client: Client) -> None:
    """Drop the pool waits whose threads cannot be woken, and wake each one whose cap has ended."""
    at = waits.where()
    held = waits.read(at)
    gone = {one.id for one in held if dead(run, client, one)}
    if gone:
        waits.forget(at, gone)
    for one in held:
        if one.id not in gone and one.due(run.now) and tell_capped(run, client, one):
            waits.forget(at, {one.id})


def tell_capped(run: Pass, client: Client, one: Wait) -> bool:
    """Send the thread its wake, and say whether the wait is done: T3 Code took the message, or
    said the thread is gone."""
    message = CAPPED.format(role=one.role, until=one.until, thread=one.thread)
    try:
        went = outbox.send(
            run,
            client,
            thread=one.thread,
            row=one.thread,
            key=f"pool-wake|{one.thread}|{one.id}",
            text=message,
            template="pool-wake",
            needs="act",
        )
    except T3Refused as error:
        if GONE.search(str(error)):
            return _gone(run, one, error)
        run.say(f"wait {one.thread}: it could not be told the {one.role} pool is free ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {one.thread}: it could not be told the {one.role} pool is free ({error})")
        return False
    if not went:
        return False
    line = (
        f"pool-wake: woke {one.thread}, the {one.role} pool was capped until {one.until},"
        f" after {waited(one, run.now)} min"
    )
    run.find("", "pool-wake", line, key=one.id)
    run.say(line)
    return True


def waited(one: Waiter | Wait, now: datetime) -> int:
    """Return the whole minutes since the thread first waited, which `jgauge sample --report`
    counts."""
    try:
        since = datetime.fromisoformat(one.since)
    except ValueError:
        return 0
    return max(0, int((now - since).total_seconds() // 60))


def tell(run: Pass, client: Client, one: Waiter) -> None:
    command = shlex.join(one.command)
    message = MESSAGE.format(lane=one.lane, command=command)
    try:
        went = outbox.send(
            run,
            client,
            thread=one.thread,
            row=one.thread,
            key=f"slot-wake|{one.thread}|{one.id}",
            text=message,
            template="slot-wake",
            needs="act",
        )
    except T3Refused as error:
        if GONE.search(str(error)):
            _gone(run, one, error)
            waiters.forget(slot.locks_dir(), {one.id})
            return
        run.say(f"wait {one.thread}: it could not be told a slot is free ({error})")
        return
    except T3Error as error:
        run.say(f"wait {one.thread}: it could not be told a slot is free ({error})")
        return
    if not went:
        return
    waiters.woken(slot.locks_dir(), one.id, run.now)
    line = (
        f"slot-wake: woke {one.thread}, a {one.lane} slot is free for `{command}`,"
        f" after {waited(one, run.now)} min"
    )
    run.find("", "slot-wake", line, key=one.id)
    run.say(line)


def wake_ended(run: Pass, client: Client) -> None:
    """Wake each thread whose own run under a slot has ended, once, and drop the runs that are
    over: woken, owed no wake, or held by a holder that died with no end recorded."""
    locks = slot.locks_dir()
    if not holders.FILE.there(locks):
        return
    over = set()
    for one in holders.read(locks):
        if one.ended and tell_ended(run, client, one):
            over.add(one.id)
        elif not one.ended and not holders.running(one):
            over.add(one.id)
    if over:
        holders.forget(locks, over)


def tell_ended(run: Pass, client: Client, one: Holder) -> bool:
    """Send the thread the end of its run, where it is owed, and say whether the run is over: the
    message went, or the thread is gone or ended, or its own turn got the end, so that it is owed
    none."""
    try:
        asked = {"threadId": one.thread, "limit": 1, "runLimit": RUNS}
        read = client.call("t3_thread_read", asked)
    except T3Refused as error:
        if GONE.search(str(error)):
            run.say(f"wait {one.thread}: its run under a slot is dropped, its thread is gone")
            return True
        run.say(f"wait {one.thread}: the end of its run under a slot could not be told ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {one.thread}: the end of its run under a slot could not be told ({error})")
        return False
    thread: dict[str, Any] = read.get("thread") or {}
    if thread.get("settled") or thread.get("archived") or thread.get("status") in OVER:
        return True
    if any(_got_end(one, turn) for turn in read.get("recentRuns") or [] if isinstance(turn, dict)):
        return True
    if at_work([thread]):
        return False
    command = shlex.join(one.command)
    try:
        went = outbox.send(
            run,
            client,
            thread=one.thread,
            row=one.thread,
            key=f"slot-end|{one.thread}|{one.since}",
            text=ENDED_RUN.format(command=command, lane=one.lane, code=one.code),
            template="slot-end",
            needs="act",
        )
    except T3Error as error:
        run.say(f"wait {one.thread}: the end of its run under a slot could not be told ({error})")
        return False
    if not went:
        return False
    line = f"slot-end: woke {one.thread}, its run of `{command}` ended with exit code {one.code}"
    run.find("", "slot-end", line, key=one.id)
    run.say(line)
    return True


def _got_end(one: Holder, turn: dict[str, Any]) -> bool:
    """Say whether `turn`, one of the thread's turns, got the end of the run: it started before
    the run did and had not ended when the run ended, so the command that held the slot answered
    into it. A later write to the thread proves nothing, since T3 Code moves `updatedAt` when
    anyone queues the thread a message."""
    began, done = turn.get("startedAt"), turn.get("completedAt")
    try:
        return (
            bool(began)
            and when(str(began)) <= when(one.since)
            and (not done or when(str(done)) >= when(one.ended))
        )
    except (TypeError, ValueError):
        return False


STEPS = (
    verbs.Step(
        "before-watch", 40, "slotwait.wake", lambda half: wake(half.run, half.client), ("client",)
    ),
    verbs.Step(
        "before-watch",
        41,
        "slotwait.wake_capped",
        lambda half: wake_capped(half.run, half.client),
        ("client",),
    ),
    verbs.Step(
        "before-watch",
        42,
        "slotwait.wake_ended",
        lambda half: wake_ended(half.run, half.client),
        ("client",),
    ),
)
