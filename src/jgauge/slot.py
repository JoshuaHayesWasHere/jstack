"""A test slot: run one command while holding one of N lock files, machine-wide.

A slot is a `flock` on `~/.local/state/locks/test-slot.<n>.lock`, held by this process and
not by the command, so it is free again when the command ends or when this process dies.

There are two lanes. The full lane is for a whole suite and has N slots. The short lane is
for a run of a second or a minute, a reviewer's proof or a crewmate's targeted tests: it has
slots of its own, `test-slot-short.<n>.lock`, so it never waits behind a full suite, and a
command in it is stopped at its time limit, so a full suite cannot sit there. A short command
runs in a process group of its own, and the stop and every signal go to the whole group: a
`sh -c` wrapper does not leave its pytest running once the slot is free. Out of the terminal's
group, an interrupt reaches it only through this process, which passes it on.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT = 2
SHORT_SLOTS = 3
SHORT_LIMIT_SECONDS = 120.0
LOOK_EVERY_SECONDS = 0.2
STOP_GRACE_SECONDS = 5.0
TIMED_OUT = 124


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
    return Lane("test-slot-short", SHORT_SLOTS, f"{SHORT_SLOTS} short slots", SHORT_LIMIT_SECONDS)


class BadCount(Exception):
    """The number of slots asked for is not a number of slots."""


def count(asked: str | None) -> int:
    named, value = "--slots", asked
    if value is None:
        named, value = "TEST_SLOTS", os.environ.get("TEST_SLOTS")
    if value is None:
        return DEFAULT
    if not value.isdecimal() or int(value) < 1:
        raise BadCount(f"{named} is {value!r}, and the number of slots is 1 or more")
    return int(value)


def _first_free(locks: Path, lane: Lane) -> int | None:
    for n in range(1, lane.slots + 1):
        held = os.open(locks / f"{lane.lock}.{n}.lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(held)
        else:
            return held
    return None


def take(lane: Lane) -> int:
    locks = Path.home() / ".local" / "state" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    said = False
    while (held := _first_free(locks, lane)) is None:
        if not said:
            print(f"test-slot: waiting for one of {lane.called}", file=sys.stderr, flush=True)
            said = True
        time.sleep(LOOK_EVERY_SECONDS)
    return held


def _signal(child: subprocess.Popen, number: int, lane: Lane) -> None:
    """Tell the command, and in the short lane every process it started, which is its group."""
    if lane.limit is None:
        child.send_signal(number)
        return
    try:
        os.killpg(child.pid, number)
    except ProcessLookupError:
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


def run(command: list[str], lane: Lane) -> int:
    held = take(lane)
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
        child = subprocess.Popen(command, process_group=None if lane.limit is None else 0)
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
        os.close(held)
