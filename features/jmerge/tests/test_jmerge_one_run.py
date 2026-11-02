"""One run of `jmerge` that may merge runs at a time, whoever started it: jbus's pass, jbus's
merge tick, or a hand run. A run waits for another to end, and with `--if-free` it does nothing
and exits 75, so the tick tries again on its next round. The tests run the command against a
real origin and a fake `gh` (`test_jmerge_fresh.py`), while the test holds the run lock as
another run would."""

import fcntl
import sys
import threading
import time

from jmerge import lock
from test_jmerge_fresh import LINES
from test_jmerge_fresh import kitchen as kitchen  # noqa: F401


def held(kitchen):
    """Hold the run lock as another run of `jmerge` would, from another open of its file."""
    other = open(kitchen.home.state / lock.RUN, "a")
    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return other


def asked(kitchen):
    """Whether the run asked GitHub anything: the fake `gh` keeps each call in `calls`."""
    return (kitchen.home.stub / "calls").exists()


def test_a_run_with_if_free_does_nothing_while_another_run_holds_the_lock(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    said = kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --if-free'
    )
    assert kitchen.home.code == lock.BUSY
    assert said == [lock.BUSY_LINE.format(path=kitchen.home.state / lock.RUN)]
    assert not asked(kitchen)
    other.close()
    (merged,) = kitchen.run("--if-free")
    assert merged.startswith("merged 6 one ")


def test_a_run_waits_for_the_other_run_to_end_and_then_merges(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    said = []
    waiting = threading.Thread(target=lambda: said.extend(kitchen.run()))
    waiting.start()
    time.sleep(1)
    assert waiting.is_alive() and not asked(kitchen)
    other.close()
    waiting.join(timeout=60)
    (merged,) = said
    assert merged.startswith("merged 6 one ")


def test_a_check_takes_no_lock(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    (ready,) = kitchen.run("--check")
    assert ready.startswith("ready 6 ")
    other.close()
