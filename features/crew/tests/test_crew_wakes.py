"""Before a crewmate ends its turn on the pull request, it asks `jbus wakes` whether a wake can
come. While the project's home thread is failing, the block says to stay and check by hand.

The test runs the skill's block as an agent does, with the real `jbus` and a `uv` stand-in that
drops `run --project`, against the kitchen of `test_jbus_kitchen`, whose T3 Code refuses the sends
to the home thread when told to."""

import os
import subprocess

import test_room as room
from crew_helpers import block
from test_jbus_signal import later
from test_jbus_wake_failing import refusing


def wakes(kitchen):
    room.uv(kitchen.stub)
    found = block("Stay on the pull request", "jbus wakes")
    assert "sleep 240" in found
    ran = subprocess.run(
        ["sh", "-c", found.replace("sleep 240", "sleep 0")],
        capture_output=True,
        text=True,
        env={**os.environ, "T": str(kitchen.root / "templates")},
        cwd=kitchen.checkout,
        check=True,
    )
    return ran.stdout.splitlines()


def test_a_crewmate_ends_its_turn_while_the_home_thread_takes_wakes(kitchen):
    assert wakes(kitchen) == ["end your turn: wakes go: the home thread of demo is not failing"]


def test_a_crewmate_stays_in_its_turn_while_the_home_thread_is_failing(kitchen):
    refusing(kitchen)
    for number in range(3):
        kitchen.poll(later(5 * number))
    (said,) = wakes(kitchen)
    assert said.startswith("stay: wakes fail: alert: home thread demo failed 3 times in a row")
