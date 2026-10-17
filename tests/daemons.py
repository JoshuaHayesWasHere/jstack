"""The long-lived processes a test starts, and the guarantee that none outlives it.

`start` runs a command as a daemon of the test: in a session of its own, so that stopping it
reaches what it started, and with `PR_SET_PDEATHSIG` set to SIGKILL, so that a pytest killed
outright (a SIGKILL, the kernel's OOM kill, `os._exit` from pytest-timeout's thread method)
takes its daemons down with it. Nothing else could: a killed process runs no finalizer.
Every daemon is also registered, and the autouse fixture `no_daemons_left` stops each one at
the end of the test, whether it passed, failed an assert or timed out.

The kernel signals a child when the thread that started it ends, not the process, so a daemon
is started from the thread that runs the test, as pytest runs it.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys

import pytest

# Run in the child before the command: ask for SIGKILL when the parent dies, and then give up
# if it died before the request (a child whose parent is gone has a new parent, and the
# request would never fire). `exec` keeps the setting for the command.
GUARD = """\
import ctypes, os, signal, sys
parent = int(sys.argv[1])
if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent:
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
    """Stop the daemon and what it started: SIGTERM to its session, and SIGKILL to it if it has
    not ended in `STOPPED_WITHIN` seconds. Gives back what it printed, if its output was piped.
    Safe to repeat, and on a daemon that has ended."""
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
    """Stop every registered daemon, each one even when stopping another raised."""
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
