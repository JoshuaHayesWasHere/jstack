"""`daemons.stop` ends a daemon and what it started, whatever the daemon does with SIGTERM."""

import os
import subprocess
import sys
import time

import daemons

DEAF_TO_TERM = 'trap "" TERM; sh -c \'trap "" TERM; sleep 60\' & echo $!; wait'


def listed(pid: int) -> bool:
    ps = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(ps.stdout.strip()) and not ps.stdout.startswith("Z")


def until(check, seconds: float) -> None:
    """Wait up to `seconds` for `check`: the kernel takes a killed child down a moment later."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.02)
    assert check()


def test_a_daemon_that_ignores_sigterm_is_killed_with_what_it_started(monkeypatch):
    monkeypatch.setattr(daemons, "STOPPED_WITHIN", 0.5)
    stubborn = daemons.start(
        ["sh", "-c", DEAF_TO_TERM],
        stdout=subprocess.PIPE,
        text=True,
    )
    child = int(stubborn.stdout.readline())

    start = time.monotonic()
    daemons.stop(stubborn)

    assert stubborn.poll() is not None
    assert time.monotonic() - start < 5
    until(lambda: not listed(child), 2)


def test_stopping_a_daemon_twice_is_the_same_as_once():
    sleeper = daemons.start(["sleep", "60"], stdout=subprocess.PIPE, text=True)

    daemons.stop(sleeper)
    daemons.stop(sleeper)

    assert sleeper.poll() is not None


def test_stop_all_stops_every_daemon_that_was_started():
    sleepers = [daemons.start(["sleep", "60"]) for _ in range(3)]

    daemons.stop_all()

    assert [sleeper.poll() is not None for sleeper in sleepers] == [True] * 3
    assert daemons.running == []


NO_PRCTL = """\
import ctypes
class Library:
    def __init__(self, *args, **kwargs):
        pass
ctypes.CDLL = Library
"""


def test_the_guard_runs_the_command_on_a_system_with_no_prctl_such_as_macos():
    """macOS has no `prctl`, so there the guard asks for no signal and still runs the command:
    the autouse fixture alone stops the daemon there."""
    ran = subprocess.run(
        [sys.executable, "-c", NO_PRCTL + daemons.GUARD, str(os.getpid()), "echo", "ran"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (ran.returncode, ran.stdout) == (0, "ran\n")
