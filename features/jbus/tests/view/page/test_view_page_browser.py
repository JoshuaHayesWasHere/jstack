"""The browser the page's tests open: its lock, its bound, and every process it started."""

import fcntl
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, browse, heavy, look

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


@pytest.fixture
def own_home(tmp_path, monkeypatch):
    """A home of the test's own, with a locks directory, so its lock is nobody else's and it
    waits on no lock of the machine's."""
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return locks


def test_a_long_temporary_directory_does_not_fail_the_browser(scene, tmp_path, monkeypatch):
    """Chromium binds a socket in a directory it makes under TMPDIR, and the path of a socket
    holds 107 characters."""
    long = tmp_path / ("t" * max(1, 89 - len(str(tmp_path))))
    long.mkdir()
    assert len(str(long)) >= 90
    monkeypatch.setenv("TMPDIR", str(long))
    assert look(scene, tmp_path)["errors"] == []


def test_a_run_under_the_heavy_suite_lock_is_not_waited_on(own_home, monkeypatch):
    """The user's rule runs a suite of several workers under `flock` on the heavy-suite lock.
    The two locks are files of their own names in one directory, here a made-up one."""
    monkeypatch.setattr("view.page.browser.PATIENCE", 1)
    with open(own_home / "heavy-suite.lock", "a") as outer:
        fcntl.flock(outer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with heavy():
            pass


def test_two_runs_at_once_never_have_a_browser_each(own_home, monkeypatch):
    """Each thread opens the lock's file anew, as each run of this file does."""
    inside, most, start = [], [], threading.Barrier(2)

    class Browser:
        pid, returncode = 0, 0

        def __init__(self, command, **how):
            pass

        def __enter__(self):
            inside.append(1)
            most.append(len(inside))
            return self

        def communicate(self, timeout):
            time.sleep(0.3)
            return "", ""

        def __exit__(self, *raised):
            inside.pop()

    def run():
        start.wait()
        with heavy():
            browse()

    monkeypatch.setattr(subprocess, "Popen", Browser)
    monkeypatch.setattr(os, "killpg", lambda group, sent: None)
    runs = [threading.Thread(target=run) for _ in range(2)]
    for one in runs:
        one.start()
    for one in runs:
        one.join()
    assert most == [1, 1]


def test_a_browser_that_never_finishes_is_stopped_with_every_process_it_started(
    own_home, tmp_path, monkeypatch
):
    """A browser that hangs, and a process it started that would outlive it, are both gone
    once the launch's bound is up: a hang costs the test that bound and no more, and leaves
    nothing behind."""
    child = hanging(tmp_path, monkeypatch)
    monkeypatch.setattr("view.page.browser.LAUNCH", 2)
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="the browser did not finish in 2 s"):
        browse("http://127.0.0.1:9/")
    assert time.monotonic() - started < 20
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def test_a_browser_that_ignores_term_is_killed_and_named_too(own_home, tmp_path, monkeypatch):
    """`timeout` then kills its whole group, itself with it, and the run ends on a signal."""
    child = hanging(tmp_path, monkeypatch, "trap '' TERM\n")
    monkeypatch.setattr("view.page.browser.LAUNCH", 2)
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="the browser did not finish in 2 s"):
        browse("http://127.0.0.1:9/")
    assert time.monotonic() - started < 20
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def test_a_browser_stopped_from_outside_leaves_no_process_it_started(
    own_home, tmp_path, monkeypatch
):
    """pytest-timeout stops a test with a signal: the browser and what it started go too."""
    child = hanging(tmp_path, monkeypatch)

    def stops(*caught):
        raise TimeoutError("stopped from outside")

    before = signal.signal(signal.SIGALRM, stops)
    bound = signal.getitimer(signal.ITIMER_REAL)
    signal.alarm(2)
    try:
        with pytest.raises(TimeoutError):
            browse("http://127.0.0.1:9/")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, before)
        signal.setitimer(signal.ITIMER_REAL, *bound)
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def hanging(tmp_path, monkeypatch, first=""):
    """A browser that never finishes, and starts a process that would outlive it: the file
    that holds that process's id. `first` is shell it runs before."""
    child = tmp_path / "child"
    hangs = tmp_path / "chromium"
    hangs.write_text(f"#!/bin/sh\n{first}sleep 300 &\necho $! > {child}\nexec sleep 300\n")
    hangs.chmod(0o755)
    monkeypatch.setattr("view.page.browser.CHROMIUM", str(hangs))
    return child
