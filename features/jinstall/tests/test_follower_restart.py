"""`jinstall.kinds.restart`: a running service the install turns on (the follower, and the relay
where its keys are there) that started before ~/.local/bin/jbus changed runs old code, so the
install and the green move restart it, once, and a manager's refusal is said."""

import os
import time
from datetime import UTC, datetime

import pytest

from jinstall.kinds import Found, State, Units, restart, stale, unit_templates
from jinstall.machine import Machine, Ran, Refused
from testing.paths import REPO

FOLLOWER = "jbus-follow.service"
RELAY = "jbus-relay.service"


class Manager:
    """A stand-in for `systemctl --user` that reads this HOME, with each service in `state`,
    started at `started`, or at its own start in `starts`, and whose try-restart answers
    `refuses` when it is set."""

    def __init__(self, home):
        self.home = home
        self.state = "active"
        self.started = datetime.now(UTC)
        self.starts = {}
        self.refuses = ""
        self.restarted = []
        self.changed = []

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
            started = self.starts.get(asked[-1], self.started)
            at = started.strftime("%a %Y-%m-%d %H:%M:%S.%f UTC")
            return Ran(0, f"ActiveState={self.state}\nActiveEnterTimestamp={at}\n")
        if asked[0] in ("daemon-reload", "enable"):
            self.changed.append(" ".join(asked))
            return Ran(0, "")
        if asked[0] == "try-restart":
            if self.refuses:
                return Ran(1, f"{self.refuses}\n")
            self.restarted.append(asked[1])
            self.starts[asked[1]] = datetime.now(UTC)
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


class Keys:
    """The relay's need, as `RelayKeys` answers it while the relay's env file holds its keys."""

    def probe(self, machine):
        return Found.ok()


def test_a_running_relay_of_the_jbus_before_an_update_is_restarted_once_with_the_follower(
    machine,
):
    """sa-follow-runs-live: an install that changed jbus restarted the follower and left the
    relay, an opted service, on the jbus of before until its next restart."""
    machine, manager = machine
    units = machine.home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    for name in (FOLLOWER, RELAY):
        (units / name).symlink_to(unit_templates(REPO)[name])
    need = Units(units, (FOLLOWER, RELAY), (FOLLOWER,), machine.home / "none", ((RELAY, Keys()),))
    manager.starts[FOLLOWER] = datetime.now(UTC)
    manager.starts[RELAY] = datetime.now(UTC).replace(year=2020)
    changed(machine, ago=60)
    found = need.probe(machine)
    assert (found.state, found.detail.split()[0]) == (State.OLD, RELAY)
    need.restart(machine)
    need.restart(machine)
    assert manager.restarted == [RELAY]
    assert need.probe(machine).state is State.OK


def test_add_links_enables_and_starts_each_unit_with_no_link_once_services_first(machine):
    """The green move's add: each unit that is to be on and has no link, as one main added, is
    linked, then systemd reloads and enables it, services first; a second call adds nothing, and
    a machine whose install linked none of the units gets none."""
    machine, manager = machine
    units = machine.home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    templates = unit_templates(REPO)
    old, new = sorted(name for name in templates if name.endswith(".timer"))[:2]
    need = Units(units, (FOLLOWER, old, new), (new, old, FOLLOWER), machine.home / "none")
    assert need.add(machine) == []
    (units / old).symlink_to(templates[old])

    assert need.add(machine) == [FOLLOWER, new]
    for name in (FOLLOWER, old, new):
        assert (units / name).readlink() == templates[name]
    assert manager.changed == ["daemon-reload", f"enable --now {FOLLOWER}", f"enable --now {new}"]
    assert need.add(machine) == []
    assert len(manager.changed) == 3
