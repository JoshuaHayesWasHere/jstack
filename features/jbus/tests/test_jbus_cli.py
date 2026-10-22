"""`jbus poll` takes a lock. A pass that finds the lock taken prints `busy` and runs nothing, so two
passes at once run `jmerge` only once. Like `test_jbus_kitchen.py`, the tests run the real pass
against the fakes.
"""

import fcntl
import threading


def test_a_pass_that_finds_the_lock_held_prints_busy_and_runs_nothing(kitchen):
    kitchen.state_dir.mkdir()
    with open(kitchen.state_dir / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert kitchen.poll() == ["busy"]
    assert kitchen.log("jmerge") == [] and kitchen.t3.calls == []


def test_two_passes_at_once_run_jmerge_once(kitchen):
    kitchen.set("jmerge-sleep", "0.5")
    said = []
    passes = [threading.Thread(target=lambda: said.append(kitchen.poll())) for _ in range(2)]
    for one in passes:
        one.start()
    for one in passes:
        one.join()
    assert sorted(lines == ["busy"] for lines in said) == [False, True]
    assert kitchen.log("jmerge") == [""]
