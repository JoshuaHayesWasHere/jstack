"""This module holds a test that starts a relay and then fails, hangs, or is killed.
`test_jbus_relay.py` runs it in a pytest of its own and looks at what it leaves.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_relay.py` names this
file. The relay's pid goes to `LEAVES_PIDFILE` once the relay listens. `LEAVES_HOW` is what the test
does next: `fail` asserts false, and `hang` sleeps until something ends it.

The relay starts in a fixture, so that a timeout given with `timeout_func_only` times the hang
alone: a relay slow to listen on a loaded runner is not a test that timed out.
"""

import os
import time
from pathlib import Path

import pytest

import test_jbus_relay as relays

hooks = relays.hooks


@pytest.fixture
def relay(hooks, tmp_path):
    relay = relays.Relay(relays.env_for(hooks), tmp_path / "state").up()
    Path(os.environ["LEAVES_PIDFILE"]).write_text(str(relay.process.pid))
    return relay


def test_a_relay_is_started_and_the_test_does_not_finish_well(relay):
    if os.environ["LEAVES_HOW"] == "hang":
        time.sleep(100)
    raise AssertionError("the test fails with its relay still running")
