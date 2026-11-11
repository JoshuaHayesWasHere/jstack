"""A move of the green copy whose install fails goes back (`jbus.green`): it points the link at the
tree it came from, installs the tool again from that tree, since uv may have removed
~/.local/bin/jbus before it failed, and owes systemd no reload for the tip it removed. While a
move is owed, jinstall reads the link as the copy, also where it dangles.

The tests run the real pass against the kitchen's fakes, as `test_jbus_green.py` does, whose
fixtures they use."""

import json
import shutil
from dataclasses import replace

import pytest

from jbus import green
from jinstall.green import GreenCopy
from jinstall.kinds import State
from jinstall.machine import Machine
from test_green_step import Died
from test_jbus_green import TIMER, at, calls, copied, installs, land, systemctl
from test_jbus_queue import gates

FIXTURES = (copied, installs, systemctl)
"""The fixtures of `test_jbus_green.py` these tests take, which pytest finds in this module."""


def test_a_move_whose_install_fails_after_removing_the_tool_puts_it_back_and_owes_no_reload(
    copied, monkeypatch, systemctl, tmp_path
):
    """uv's `tool install --reinstall` removes the tool before it builds the new one, so an
    install that fails can leave no ~/.local/bin/jbus, and the units fail with 203/EXEC until a
    later move. The move that goes back installs the tool again from the tree it went back to,
    and the reload it wrote for the tip it removed goes with that tip."""
    tool = tmp_path / "bin" / "jbus"
    tool.parent.mkdir()
    tool.write_text("first\n")
    asked = []
    new = land(copied, "success", {"features/jbus/units/jbus.timer": TIMER.format("1min")})

    def reinstall(copy):
        asked.append(copy.resolve())
        tool.unlink(missing_ok=True)
        if copy.resolve().name == new:
            return "error: Failed to build `jstack`"
        tool.write_text(f"{copy.resolve().name}\n")
        return ""

    monkeypatch.setattr(green, "_reinstall", reinstall)
    systemctl.unlink(missing_ok=True)
    copied.poll()

    trees = green.trees(copied.copy)
    assert at(copied.copy) == copied.first
    assert asked == [trees / new, trees / copied.first]
    assert tool.read_text() == f"{copied.first}\n"
    record = json.loads((copied.state / green.FILE).read_text())
    assert [key for key in green.OWED if key in record] == []
    assert green.MOVE not in record
    assert "--user daemon-reload" not in calls(systemctl)
    assert gates(copied) == [f"condition green: {green.MOVE_FAILED}"]


def test_an_install_back_that_uv_refuses_too_is_asked_again_before_any_new_move(
    copied, monkeypatch
):
    """Where uv refuses the tree the move went back to as well, the tool may be gone: the install
    of that tree stays owed, and each pass asks for it before it tries main's tip again."""
    asked, broken = [], [True]
    new = land(copied, "success")

    def reinstall(copy):
        asked.append(copy.resolve().name)
        return "error: uv is broken" if broken[0] else ""

    monkeypatch.setattr(green, "_reinstall", reinstall)
    copied.poll()
    assert asked == [new, copied.first]
    assert at(copied.copy) == copied.first

    copied.poll()
    assert asked == [new, copied.first, copied.first, new, copied.first]
    assert at(copied.copy) == copied.first
    assert sorted(path.name for path in green.trees(copied.copy).iterdir()) == [copied.first]

    broken[0] = False
    copied.poll()
    assert asked[5:] == [copied.first, new]
    assert at(copied.copy) == new


def test_an_old_tree_uv_never_takes_again_does_not_stop_a_newer_green_tip(copied, monkeypatch):
    """A move went back to a tree whose install uv refuses for good, as with a lock that names a
    wheel the index dropped, so its install stays owed. Main's next green tip, which uv takes,
    replaces it on the next pass: the copy and the tool are at that tip, and no move is owed."""
    tool, refused = [], {copied.first}
    new = land(copied, "success")
    refused.add(new)

    def reinstall(copy):
        name = copy.resolve().name
        if name in refused:
            return "error: Distribution not found at: https://files.example/gone.whl"
        tool.append(name)
        return ""

    monkeypatch.setattr(green, "_reinstall", reinstall)
    copied.poll()
    assert at(copied.copy) == copied.first
    assert green.in_flight(copied.state) == {
        "to": copied.first,
        "from": copied.first,
        "owes": "install",
    }

    newer = land(copied, "success")
    copied.poll()
    assert at(copied.copy) == newer
    assert tool == [newer]
    assert green.in_flight(copied.state) is None


def test_a_dangling_link_with_a_move_owed_is_the_copy_and_not_foreign(copied, monkeypatch):
    """A pass died after it pointed the link, and a hand removed the tree it pointed at: the
    link dangles until the next pass puts it back. jinstall reads it as the copy, through the
    tree the owed move came from, so an install in between neither calls it foreign nor fails."""

    def killed(copy):
        raise Died

    monkeypatch.setattr(green, "_reinstall", killed)
    new = land(copied, "success")
    with pytest.raises(Died):
        copied.poll()
    shutil.rmtree(green.trees(copied.copy) / new)
    assert not copied.copy.exists() and copied.copy.is_symlink()

    machine = replace(Machine.here(copied.checkout), green=copied.copy)
    found = GreenCopy(copied.copy).probe(machine)
    assert (found.state, found.replaceable) == (State.OK, True), found.detail
    assert found.detail.startswith(f"mid-move to {new[:12]}"), found.detail
