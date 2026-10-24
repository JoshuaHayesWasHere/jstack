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
- A wake is one `t3_thread_send` in mode queue, keyed by the wait, so a retry sends the same
  message. jbus records the wait as woken only after T3 Code took the message. So jbus wakes
  each wait once, and sends again a message that got no answer.

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

from jbus import END_TURN, verbs
from jbus.passes import Pass
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.watch import ENDED
from jgauge import slot, waiters
from jgauge.waiters import Waiter
from jroles import waits
from jroles.waits import Wait

EVENTS = {"slot-wake": "quiet", "pool-wake": "quiet"}
OVER = (*ENDED, "rolled_back")
MESSAGE = (
    "jbus: a {lane} test slot is free. Run again what you waited to run: `{command}`. If every"
    " slot is taken again by then, register again and end your turn: jbus wakes you once for"
    " each wait. " + END_TURN
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
    client.recipients = client.recipients | {one.thread}
    asked = {
        "threadId": one.thread,
        "message": message,
        "mode": "queue",
        "clientRequestId": f"pool-wake|{one.thread}|{one.id}",
    }
    try:
        client.call("t3_thread_send", asked)
    except T3Refused as error:
        if GONE.search(str(error)):
            return _gone(run, one, error)
        run.say(f"wait {one.thread}: it could not be told the {one.role} pool is free ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {one.thread}: it could not be told the {one.role} pool is free ({error})")
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
    client.recipients = client.recipients | {one.thread}
    asked = {
        "threadId": one.thread,
        "message": message,
        "mode": "queue",
        "clientRequestId": f"slot-wake|{one.thread}|{one.id}",
    }
    try:
        client.call("t3_thread_send", asked)
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
    waiters.woken(slot.locks_dir(), one.id, run.now)
    line = (
        f"slot-wake: woke {one.thread}, a {one.lane} slot is free for `{command}`,"
        f" after {waited(one, run.now)} min"
    )
    run.find("", "slot-wake", line, key=one.id)
    run.say(line)


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
)
