"""A test that starts a relay and then fails, hangs, or is killed, for `test_jbus_relay.py` to
run in a pytest of its own and look at what it leaves.

Not collected: the name has no `test_` prefix, and `test_jbus_relay.py` names this file.
`LEAVES_PIDFILE` is where the relay's pid is written once it listens, and `LEAVES_HOW` is
what the test does next: `fail` asserts false, `hang` sleeps until something ends it.
"""

import os
import time
from pathlib import Path

import test_jbus_relay as relays

hooks = relays.hooks


def test_a_relay_is_started_and_the_test_does_not_finish_well(hooks, tmp_path):
    relay = relays.Relay(relays.env_for(hooks), tmp_path / "state").up()
    Path(os.environ["LEAVES_PIDFILE"]).write_text(str(relay.process.pid))
    if os.environ["LEAVES_HOW"] == "hang":
        time.sleep(100)
    raise AssertionError("the test fails with its relay still running")
