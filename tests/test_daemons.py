"""`daemons.stop` ends a daemon whatever it does with SIGTERM, and what it started."""

import subprocess
import time

import daemons

DEAF_TO_TERM = 'trap "" TERM; sh -c \'trap "" TERM; sleep 60\' & echo $!; wait'


def listed(pid: int) -> bool:
    ps = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(ps.stdout.strip()) and not ps.stdout.startswith("Z")


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

    assert stubborn.poll() is not None and not listed(child)
    assert time.monotonic() - start < 5


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
