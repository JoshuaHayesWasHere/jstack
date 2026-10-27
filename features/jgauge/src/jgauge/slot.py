"""A test slot: run one command while holding one of N lock files, machine-wide.

A slot is a `flock` on `~/.local/state/locks/test-slot.<n>.lock`. This process holds it, not
the command, so the slot is free again when the command ends or when this process dies.

There are two lanes. The full lane is for a whole suite and has N slots, `test_slots` in
`jgauge.sizes`. That module derives the count from the machine unless `--slots`, `TEST_SLOTS`
or the local machine file sets it. The short lane is for a run of a second or a minute, such as
a reviewer's proof or a crewmate's targeted tests. It has slots of its own, `short_slots` in the
same module, with the lock files `test-slot-short.<n>.lock`, so it never waits behind a full
suite. This process stops a command in the short lane at its time limit, so a full suite cannot
keep a short slot. A short command runs in a process group of its own, and the stop and every
signal go to the whole group: a `sh -c` wrapper does not leave its pytest running once the slot
is free. Since that group is out of the terminal's group, an interrupt reaches the command only
through this process, which passes it on.

A thread that cannot wait in a call does not wait: `jgauge test-slot --thread <id>` tries once,
and with every slot of its lane taken it registers the thread as a waiter (`jgauge.waiters`) and
exits with code 76. `jbus poll` sends the oldest waiter of a lane one message when a slot of the
lane is free. That wake claims the slot for the thread for `waiters.HOLDS`, and another thread
with `--thread` takes a slot only while the free slots outnumber the claims of other threads:
with none to spare it registers as a waiter, as it does with every slot taken. The woken thread
then runs its command again. That run takes the slot and takes the thread out of the waiters
file, and with it its claim.

The command runs with `JGAUGE_TEST_SLOT` set to its lane, `full` or `short`, so a run it starts
knows a slot is held: a TLC model check in a suite takes no second slot, and cannot wait on the
one its own suite holds.

Each slot has a temporary directory of its own beside its lock file, `test-slot.<n>.tmp` (or
`test-slot-short.<n>.tmp`), and the command runs with `TMPDIR` set to it. So pytest's basetemp,
`pytest-of-<user>` under the temporary directory, is the slot's, for the suite and for every
pytest it starts, and nothing goes to the `pytest-of-<user>` in `/tmp` that every worktree's runs
shared. Pytest's own retention did not keep that one small: a run that was killed never cleaned
up, and runs at once shared its numbering. Only the slot's holder writes in the directory. It
removes the directory when it lets the slot go, however the command ended. A holder that dies
cannot, so the next one to take the slot removes what is left before its command starts.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jgauge import sizes, waiters

SHORT_LIMIT_SECONDS = 120.0
LOOK_EVERY_SECONDS = 0.2
STOP_GRACE_SECONDS = 5.0
TIMED_OUT = 124
WAITING = 76
HELD = "JGAUGE_TEST_SLOT"


@dataclass(frozen=True)
class Lane:
    """Which lock files a command takes, how many there are, and how long it may hold one."""

    lock: str
    slots: int
    called: str
    limit: float | None = None


def full(slots: int) -> Lane:
    return Lane("test-slot", slots, f"{slots} slots")


def short() -> Lane:
    slots = sizes.resolve(sizes.Name.SHORT_SLOTS).value
    return Lane("test-slot-short", slots, f"{slots} short slots", SHORT_LIMIT_SECONDS)


class BadCount(Exception):
    """The slot count that `--slots`, `TEST_SLOTS` or the machine file gives is not a valid
    count."""


def count(asked: str | None) -> int:
    """The full lane's slots: `--slots`, else `TEST_SLOTS`, else the machine file, else the
    machine's derived count."""
    try:
        return sizes.resolve(sizes.Name.TEST_SLOTS, flag=asked).value
    except sizes.Refused as error:
        raise BadCount(str(error)) from error


def locks_dir() -> Path:
    return Path(os.environ.get("JGAUGE_LOCKS_DIR") or Path.home() / ".local" / "state" / "locks")


def name(lane: Lane) -> str:
    return "short" if lane.limit is not None else "full"


def lane_of(kind: str, slots: int) -> Lane:
    return short() if kind == "short" else full(slots)


def free(lane: Lane) -> int:
    """How many slots of the lane no one holds now. The function tries each slot's lock and lets
    it go at once, and a lock file that is not there is a slot no one has taken."""
    locks, found = locks_dir(), 0
    for n in range(1, lane.slots + 1):
        try:
            held = os.open(locks / f"{lane.lock}.{n}.lock", os.O_RDWR)
        except FileNotFoundError:
            found += 1
            continue
        except OSError:
            continue
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            found += 1
        finally:
            os.close(held)
    return found


def _first_free(locks: Path, lane: Lane) -> tuple[int, Path] | None:
    for n in range(1, lane.slots + 1):
        lock = locks / f"{lane.lock}.{n}.lock"
        held = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(held)
        else:
            return held, lock
    return None


def take(lane: Lane, thread: str = "", command: list[str] | None = None) -> tuple[int, Path] | None:
    """Wait for a slot and take it, and give the held lock and its file. With a `thread` it does
    not wait, and leaves the free slots that woken waiters of other threads claim to them: when
    no slot is free for it, it registers the thread as a waiter on the lane, says so in one
    line, and takes no slot. A thread that takes a slot is no longer a waiter."""
    locks = locks_dir()
    locks.mkdir(parents=True, exist_ok=True)
    if thread:
        now = datetime.now(UTC)
        claimed = waiters.claims(locks, name(lane), thread, now)
        held = _first_free(locks, lane)
        if held is not None and 1 + free(lane) > claimed:
            waiters.drop(locks, thread)
            return held
        if held is not None:
            os.close(held[0])
        waiters.register(locks, thread, name(lane), lane.slots, command or [], now)
        why = (
            f"the free ones of {lane.called} are held for woken waiters"
            if held is not None
            else f"every one of {lane.called} is taken"
        )
        print(
            f"test-slot: {why}; {thread} is registered as a waiter"
            " and jbus will wake it when one is free. End your turn.",
            flush=True,
        )
        return None
    said = False
    while (held := _first_free(locks, lane)) is None:
        if not said:
            print(f"test-slot: waiting for one of {lane.called}", file=sys.stderr, flush=True)
            said = True
        time.sleep(LOOK_EVERY_SECONDS)
    return held


def _temporary(lock: Path) -> Path:
    """The temporary directory of the slot whose lock file is `lock`, emptied of what a holder
    that died left in it."""
    own = lock.with_name(f"{lock.stem}.tmp")
    shutil.rmtree(own, ignore_errors=True)
    own.mkdir(mode=0o700, exist_ok=True)
    return own


def _signal(child: subprocess.Popen, number: int, lane: Lane) -> None:
    """Send the signal to the command, and in the short lane to every process it started, which
    is its process group. A group with no process left to signal is no fault: Linux says ESRCH,
    and macOS says EPERM while a zombie of the group waits to be reaped, as an orphan does until
    launchd gets to it."""
    if lane.limit is None:
        child.send_signal(number)
        return
    try:
        os.killpg(child.pid, number)
    except (ProcessLookupError, PermissionError):
        pass


def _stop(child: subprocess.Popen, lane: Lane) -> int:
    print(
        f"test-slot: stopped {child.args[0]} at {lane.limit:g} s, the short lane's limit",
        file=sys.stderr,
        flush=True,
    )
    _signal(child, signal.SIGTERM, lane)
    try:
        child.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    _signal(child, signal.SIGKILL, lane)
    child.wait()
    return TIMED_OUT


def run(command: list[str], lane: Lane, thread: str = "", wake: list[str] | None = None) -> int:
    """Run `command` under a slot of `lane`. A waiter registers `wake`, what the thread runs
    again once jbus wakes it, which is `command` itself unless the caller names another."""
    took = take(lane, thread, wake or command)
    if took is None:
        return WAITING
    held, lock = took
    own = _temporary(lock)
    child: subprocess.Popen | None = None
    early: list[int] = []

    def pass_on(number: int, _frame: object) -> None:
        if child is None:
            early.append(number)
        else:
            _signal(child, number, lane)

    for told in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(told, pass_on)
    try:
        child = subprocess.Popen(
            command,
            env={**os.environ, HELD: name(lane), "TMPDIR": str(own)},
            process_group=None if lane.limit is None else 0,
        )
    except OSError as error:
        print(f"test-slot: {command[0]}: {error.strerror}", file=sys.stderr)
        return 126 if isinstance(error, PermissionError) else 127
    else:
        signal.signal(signal.SIGINT, signal.SIG_IGN if lane.limit is None else pass_on)
        for number in early:
            _signal(child, number, lane)
        try:
            code = child.wait(timeout=lane.limit)
        except subprocess.TimeoutExpired:
            return _stop(child, lane)
        return code if code >= 0 else 128 - code
    finally:
        shutil.rmtree(own, ignore_errors=True)
        os.close(held)
