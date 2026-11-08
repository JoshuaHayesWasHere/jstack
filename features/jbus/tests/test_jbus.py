"""These tests check what holds for the package as a whole. They check what its source imports and
names, and what the repo may hold. They check the example config and the units that run a pass. They
also check two things that `jbus/__init__.py` does for every pass: it refuses a bad config, and it
writes the status file.

The tests that run a pass run it in the kitchen of `test_jbus_kitchen`, against a faked T3 Code
server, `gh` and `jmerge`. Nothing reaches the network.
"""

import configparser
import json
import re
import shlex
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from jbus import wake
from test_jbus_kitchen import NOW, REPO


@pytest.mark.parametrize("name", ["config.toml", "t3.json"])
@pytest.mark.parametrize("mode", [0o640, 0o604])
def test_a_config_or_a_token_others_can_read_stops_jbus(kitchen, name, mode):
    (kitchen.config_dir / name).chmod(mode)
    code, said = kitchen.main("poll")
    assert code == 1
    path = kitchen.config_dir / name
    assert said == f"refused: {path} is mode {mode:03o}, readable by others: chmod 600 it\n"
    assert kitchen.log("jmerge") == []


def test_the_timer_runs_a_pass_every_minute_and_a_failed_one_runs_the_alarm():
    """The test reads the three units as systemd reads them. It also reads the commands that the
    services name."""
    units = {}
    for name in ("jbus.service", "jbus.timer", "jbus-failed.service"):
        units[name] = configparser.ConfigParser(interpolation=None, strict=False)
        units[name].optionxform = str
        units[name].read(REPO / "features" / "jbus" / "units" / name)
    service, failed = units["jbus.service"], units["jbus-failed.service"]
    for unit, verb in ((service, "poll"), (failed, "alarm")):
        command = shlex.split(unit["Service"]["ExecStart"])
        assert (Path(command[0]).name, command[1:]) == ("jbus", [verb])
        assert unit["Service"]["Type"] == "oneshot"
    assert service["Unit"]["OnFailure"] == "jbus-failed.service"
    assert units["jbus.timer"]["Timer"]["OnUnitActiveSec"] == "1min"
    assert units["jbus.timer"]["Install"]["WantedBy"] == "timers.target"


def test_jmerge_ends_before_systemd_stops_the_pass():
    """The test names each of the two limits once: what a pass allows `jmerge`, and the unit's.
    Once, at 03:26 ET, a local check ran past a later limit and was killed before it recorded
    its result."""
    service = configparser.ConfigParser(interpolation=None, strict=False)
    service.optionxform = str
    service.read(REPO / "features" / "jbus" / "units" / "jbus.service")
    started = service["Service"]["TimeoutStartSec"]
    assert re.fullmatch(r"\d+min", started)
    assert int(started.removesuffix("min")) * 60 > wake.JMERGE_TIMEOUT


def test_the_2_s_tick_never_reaches_systemds_start_limit():
    """systemd refuses a unit started more than 5 times in 10 s by default, and a 2 s timer sits at
    that edge: a reload from a green move pushed `jbus-merge.service` over it 3 times on
    2026-11-08, and one refusal cost a pull request's line a 4 s gap. The tick has no limit."""
    service = configparser.ConfigParser(interpolation=None, strict=False)
    service.optionxform = str
    service.read(REPO / "features" / "jbus" / "units" / "jbus-merge.service")
    assert service["Unit"]["StartLimitIntervalSec"] == "0"

def test_each_pass_rewrites_the_status_file_and_jbus_status_prints_it(kitchen):
    assert kitchen.main("status") == (
        1,
        f"refused: no status at {kitchen.state_dir / 'status.json'}: no pass has run\n",
    )
    kitchen.poll()
    written = {
        "alerts": [],
        "last_pass": "2026-10-12 11:00 ET",
        "projects": {
            "demo": {
                "capped": [],
                "failed_wakes": 0,
                "last_error": "",
                "sign_in": "",
                "sweep": "",
            }
        },
        "streaks": {},
        "homes_off_bus": [],
        "scratch": {},
        "token_expires": "2026-11-11 10:00 ET",
        "sign_in_reminder": (
            "sign-in to the desk on 2026-11-04, each day from 2026-11-08, "
            "and when it runs out at 2026-11-11 10:00 ET"
        ),
    }
    assert kitchen.status() == written
    assert stat.S_IMODE((kitchen.state_dir / "status.json").stat().st_mode) == 0o600
    code, said = kitchen.main("status")
    printed = json.loads(said)
    assert printed.pop("pass")["started"] == "2026-10-12T15:00:00Z"
    assert (code, printed) == (0, {**written, "closed": {}, "held_pools": []})
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.status()["last_pass"] == "2026-10-12 11:03 ET"


def test_with_no_token_the_status_file_has_no_expiry(kitchen):
    (kitchen.config_dir / "t3.json").unlink()
    kitchen.poll()
    assert kitchen.status()["token_expires"] is None
