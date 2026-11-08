"""`Units.add`, which the green move runs: a unit the install turns on whose link the move made
but whose daemon-reload or enable --now the manager refused is enabled and started by the next
move, and a move after each step was taken asks the manager for no enable."""

import pytest

from jinstall.kinds import Units, unit_templates
from jinstall.machine import Machine, Ran, Refused
from testing.paths import REPO

FOLLOWER = "jbus-follow.service"
TIMER = "jbus.timer"


class Manager:
    """A stand-in for `systemctl --user` that reads `home` (or another HOME while `elsewhere` is
    set), keeps each call, says `enabled` of each unit in `enabled`, and refuses enable --now
    with `refuses` while it is set."""

    def __init__(self, home):
        self.home = home
        self.elsewhere = False
        self.enabled = {TIMER}
        self.refuses = ""
        self.calls = []

    def __call__(self, args):
        asked = list(args[2:])
        if asked == ["show-environment"]:
            return Ran(0, f"HOME={self.home.parent if self.elsewhere else self.home}\n")
        self.calls.append(" ".join(asked))
        if asked[0] == "is-enabled":
            return Ran(0, "enabled\n") if asked[1] in self.enabled else Ran(1, "disabled\n")
        if asked[:2] == ["enable", "--now"]:
            if self.refuses:
                return Ran(1, f"{self.refuses}\n")
            self.enabled.add(asked[2])
        return Ran(0, "")


@pytest.fixture
def setup(tmp_path):
    """A machine whose install linked and enabled jbus.timer, and a tip that adds the follower."""
    home = tmp_path / "home"
    units = home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    (units / TIMER).symlink_to(unit_templates(REPO)[TIMER])
    manager = Manager(home)
    machine = Machine(REPO, home, {}, manager, tmp_path / "account")
    need = Units(units, (FOLLOWER, TIMER), (FOLLOWER, TIMER), home / "no-config.toml")
    return machine, manager, need, units


def test_a_refused_enable_is_taken_up_by_the_next_add_and_a_taken_one_is_not_asked_again(setup):
    """sa-follow-add-retries: a move that linked the follower and had enable --now refused left
    a link that no later move enabled, so the follower stayed stopped until a jinstall run."""
    machine, manager, need, units = setup
    manager.refuses = "Failed to enable unit: Access denied"
    with pytest.raises(Refused, match=f"enable --now {FOLLOWER}: Failed to enable unit"):
        need.add(machine)
    assert (units / FOLLOWER).readlink() == unit_templates(REPO)[FOLLOWER]

    manager.refuses, manager.calls = "", []
    assert need.add(machine) == [FOLLOWER]
    assert [call for call in manager.calls if not call.startswith("is-enabled")] == [
        "daemon-reload",
        f"enable --now {FOLLOWER}",
    ]

    manager.calls = []
    assert need.add(machine) == []
    assert [call for call in manager.calls if not call.startswith("is-enabled")] == []


def test_a_manager_that_reads_another_home_leaves_the_link_alone_to_decide(setup):
    machine, manager, need, units = setup
    (units / FOLLOWER).symlink_to(unit_templates(REPO)[FOLLOWER])
    manager.elsewhere = True
    assert need.add(machine) == []
    assert manager.calls == []
