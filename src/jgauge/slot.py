"""A test slot: run one command while holding one of N lock files, machine-wide.

A slot is a `flock` on `~/.local/state/locks/test-slot.<n>.lock`, held by this process and
not by the command, so it is free again when the command ends or when this process dies.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT = 2
LOOK_EVERY_SECONDS = 0.2


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


def _first_free(locks: Path, slots: int) -> int | None:
    for n in range(1, slots + 1):
        held = os.open(locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(held)
        else:
            return held
    return None


def take(slots: int) -> int:
    locks = Path.home() / ".local" / "state" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    said = False
    while (held := _first_free(locks, slots)) is None:
        if not said:
            print(f"test-slot: waiting for one of {slots} slots", file=sys.stderr, flush=True)
            said = True
        time.sleep(LOOK_EVERY_SECONDS)
    return held


def run(command: list[str], slots: int) -> int:
    held = take(slots)
    child: subprocess.Popen | None = None
    early: list[int] = []

    def pass_on(number: int, _frame: object) -> None:
        if child is None:
            early.append(number)
        else:
            child.send_signal(number)

    for told in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(told, pass_on)
    try:
        child = subprocess.Popen(command)
    except OSError as error:
        print(f"test-slot: {command[0]}: {error.strerror}", file=sys.stderr)
        return 126 if isinstance(error, PermissionError) else 127
    else:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for number in early:
            child.send_signal(number)
        code = child.wait()
        return code if code >= 0 else 128 - code
    finally:
        os.close(held)
