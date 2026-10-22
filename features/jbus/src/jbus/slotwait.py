"""Waking a thread that waits on a test slot, when a slot of its lane is free.

A thread that finds every slot taken registers in `test-slot-waiters.json` (`jgauge.waiters`,
which `jgauge test-slot --thread` writes) and ends its turn. Nothing in T3 Code resumes it, so
each pass of `jbus poll` does, in `wake`:

- A waiter whose thread is gone, settled, archived or ended is dropped (`dead`): a thread that
  ended its turn to wait is `completed`, and is alive.
- A woken wait whose thread was told long ago, and did nothing, is dropped.
- For each lane that has a slot free, the oldest waiters on it are woken, one for each free
  slot that a woken waiter has not claimed already. A woken waiter claims its slot for
  `waiters.HOLDS`: it has been told, and has not taken it yet.
- A wake is one `t3_thread_send`, mode queue, keyed by the wait, so a retry is the same message.
  It is recorded as woken only after T3 Code took it, so a wait is woken once and a message
  that got no answer is tried again.

The file is the machine's, not a project's: a pass of any project wakes any waiter, and
whichever pass records the wake first, the others see it. A thread that takes a slot leaves the
file (`jgauge.slot.take`).
"""

from __future__ import annotations

import shlex
from collections import defaultdict
from datetime import datetime
from typing import Any

from jbus import END_TURN, verbs
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import ENDED
from jgauge import slot, waiters
from jgauge.waiters import Waiter

EVENTS = {"slot-wake": "quiet"}
OVER = (*ENDED, "rolled_back")
MESSAGE = (
    "jbus: a {lane} test slot is free. Run again what you waited to run: `{command}`. If every"
    " slot is taken again by then, register again and end your turn: jbus wakes you once for"
    " each wait. " + END_TURN
)


def dead(run: Pass, client: Client, waiter: Waiter) -> bool:
    """Whether the waiter's thread cannot be woken: it is gone, settled, archived or ended with
    a failure, an interrupt or a cancel. A thread that T3 Code could not be asked about is not."""
    try:
        read = client.call("t3_thread_read", {"threadId": waiter.thread, "limit": 1})
    except T3Refused as error:
        if GONE.search(str(error)):
            return True
        run.say(f"wait {waiter.thread}: its slot wait could not be checked ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {waiter.thread}: its slot wait could not be checked ({error})")
        return False
    thread: dict[str, Any] = read.get("thread") or {}
    return bool(thread.get("settled") or thread.get("archived")) or thread.get("status") in OVER


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


def waited(one: Waiter, now: datetime) -> int:
    """Whole minutes since the thread first waited, which `jgauge sample --report` counts."""
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
)
