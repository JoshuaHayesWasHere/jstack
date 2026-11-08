"""`jinstall.kinds.restart`: a running always-on service that started before ~/.local/bin/jbus
changed runs old code, so the install restarts it, once, and a manager's refusal is said."""

import os
import time
from datetime import UTC, datetime

import pytest

from jinstall.kinds import State, Units, restart, stale, unit_templates
from jinstall.machine import Machine, Ran, Refused
from testing.paths import REPO

FOLLOWER = "jbus-follow.service"


class Manager:
    """A stand-in for `systemctl --user` that reads this HOME, with the follower in `state`,
    started at `started`, and whose try-restart answers `refuses` when it is set."""

    def __init__(self, home):
        self.home = home
        self.state = "active"
        self.started = datetime.now(UTC)
        self.refuses = ""
        self.restarted = []

    def __call__(self, args):
        if list(args[:2]) != ["systemctl", "--user"]:
            return Ran(None, "")
        asked = list(args[2:])
        if asked == ["show-environment"]:
            return Ran(0, f"HOME={self.home}\n")
        if asked[0] == "is-enabled":
            return Ran(0, "enabled\n")
        if asked[:2] == ["show", "--property"]:
            return Ran(0, "no\n")
        if asked[0] == "show":
            at = self.started.strftime("%a %Y-%m-%d %H:%M:%S.%f UTC")
            return Ran(0, f"ActiveState={self.state}\nActiveEnterTimestamp={at}\n")
        if asked[0] == "try-restart":
            if self.refuses:
                return Ran(1, f"{self.refuses}\n")
            self.restarted.append(asked[1])
            self.started = datetime.now(UTC)
            return Ran(0, "")
        return Ran(64, f"no stand-in for {asked}")


@pytest.fixture
def machine(tmp_path):
    home = tmp_path / "home"
    jbus = home / ".local" / "bin" / "jbus"
    jbus.parent.mkdir(parents=True)
    jbus.write_text("#!/bin/sh\n")
    manager = Manager(home)
    return Machine(REPO, home, {}, manager, tmp_path / "account"), manager


def changed(machine, ago=0.0):
    """Mark ~/.local/bin/jbus as installed `ago` seconds ago, as uv's reinstall does."""
    when = time.time() - ago
    os.utime(machine.home / ".local" / "bin" / "jbus", (when, when))


def test_a_follower_that_started_before_jbus_changed_is_old_and_restarted_once(machine):
    machine, manager = machine
    units = machine.home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    (units / FOLLOWER).symlink_to(unit_templates(REPO)[FOLLOWER])
    need = Units(units, (FOLLOWER,), (FOLLOWER,), machine.home / "no-config.toml")
    manager.started = datetime.now(UTC).replace(year=2020)
    changed(machine)
    found = need.probe(machine)
    jbus = machine.home / ".local" / "bin" / "jbus"
    said = f"{FOLLOWER} started before {jbus} changed, so it runs old code"
    assert (found.state, found.detail) == (State.OLD, said)
    restart(machine, (FOLLOWER,))
    restart(machine, (FOLLOWER,))
    assert manager.restarted == [FOLLOWER]
    assert need.probe(machine).state is State.OK


def test_a_follower_started_after_jbus_changed_or_not_running_is_left(machine):
    machine, manager = machine
    changed(machine, ago=3600)
    assert stale(machine, (FOLLOWER, "jbus.timer")) == []
    manager.state, manager.started = "inactive", datetime.now(UTC).replace(year=2020)
    assert stale(machine, (FOLLOWER,)) == []
    (machine.home / ".local" / "bin" / "jbus").unlink()
    manager.state = "active"
    assert stale(machine, (FOLLOWER,)) == []


def test_a_restart_the_manager_refuses_says_what_it_said(machine):
    machine, manager = machine
    manager.started = datetime.now(UTC).replace(year=2020)
    manager.refuses = "Failed to restart jbus-follow.service: Access denied"
    with pytest.raises(Refused, match=f"try-restart {FOLLOWER}: Failed to restart"):
        restart(machine, (FOLLOWER,))
