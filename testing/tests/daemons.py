"""The long-lived processes a test starts, and the guarantee that none outlives it.

`start` runs a command as a daemon of the test. The daemon runs in a session of its own, so that
stopping it also stops what it started. It has `PR_SET_PDEATHSIG` set to SIGKILL, so that when
pytest is killed outright (a SIGKILL, the kernel's OOM kill, `os._exit` from pytest-timeout's thread
method), the kernel kills its daemons too. No other mechanism could stop them, since a killed
process runs no finalizer. `start` also registers every daemon, and the autouse fixture
`no_daemons_left` stops each one at the end of the test, whether it passed, failed an assert or
timed out.

The kernel signals a child when the thread that started it ends, not when the process ends. So a
test starts each daemon from the thread that pytest runs the test in.

`GUARD` is what the child runs before the command. It asks for SIGKILL when the parent dies. It
exits with code 97 if the parent died before the request, since the kernel would never send the
signal to a child whose parent is gone. Then it `exec`s the command, which keeps the setting.
macOS has no `prctl` and no such signal, so there the guard asks for nothing, and the autouse
fixture alone stops each daemon: one is left behind only when pytest itself is killed.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys

import pytest

GUARD = """\
import ctypes, os, signal, sys
parent = int(sys.argv[1])
prctl = getattr(ctypes.CDLL(None, use_errno=True), "prctl", None)
if (prctl is not None and prctl(1, signal.SIGKILL) != 0) or os.getppid() != parent:
    os._exit(97)
os.execvp(sys.argv[2], sys.argv[2:])
"""

STOPPED_WITHIN = 5.0

running: list[subprocess.Popen] = []


def start(argv: list[str], **options) -> subprocess.Popen:
    """Start `argv` as a daemon of the test, and register it for `stop_all`."""
    options.setdefault("start_new_session", True)
    process = subprocess.Popen([sys.executable, "-c", GUARD, str(os.getpid()), *argv], **options)
    running.append(process)
    return process


def stop(process: subprocess.Popen) -> str:
    """Stop the daemon and what it started. This sends SIGTERM to its session, and SIGKILL if
    the daemon has not ended in `STOPPED_WITHIN` seconds. Return what the daemon printed, if its
    caller piped its output. It is safe to call again, and on a daemon that has ended."""
    said = ""
    try:
        if process.poll() is None:
            signal_session(process, signal.SIGTERM)
        said, _ = process.communicate(timeout=STOPPED_WITHIN)
    except subprocess.TimeoutExpired:
        signal_session(process, signal.SIGKILL)
        said, _ = process.communicate()
    finally:
        if process.poll() is None:
            signal_session(process, signal.SIGKILL)
            process.wait()
    return said or ""


def signal_session(process: subprocess.Popen, number: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, number)


def stop_all() -> None:
    """Stop every registered daemon, and stop each one even when stopping another daemon
    raised an error."""
    failed = []
    while running:
        process = running.pop()
        try:
            stop(process)
        except Exception as error:
            failed.append(error)
    if failed:
        raise failed[0]


@pytest.fixture(autouse=True)
def no_daemons_left():
    yield
    stop_all()
