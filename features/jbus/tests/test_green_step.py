"""A move of the green copy (`jbus.green`) takes steps: it points the link at the new tip's tree,
installs the tool again from it, and puts the harness layouts again. `green.json` keeps the step
the move owes, written before the link moves, and the next pass resumes it before it reads
main.json, so a pass that dies between two steps, or a step that is refused, costs one pass and
never leaves the link at one tip and the tool or the layouts at another.

The tests run the real pass against the kitchen's fakes, as `test_jbus_green.py` does, whose
fixtures they use."""

import shutil

import pytest

from jbus import green
from jinstall import green as jinstall_green
from test_jbus_green import at, copied, installs, land, systemctl
from test_jbus_queue import gates

FIXTURES = (copied, installs, systemctl)
"""The fixtures of `test_jbus_green.py` these tests take, which pytest finds in this module:
the copy at main's first green tip, the installs a move made, and the systemctl it calls."""


class Died(BaseException):
    """The pass is killed: a timeout, a reboot, an OOM kill. No step of the pass catches it."""


def test_a_move_killed_after_the_link_is_pointed_is_installed_by_the_next_pass(
    copied, monkeypatch, installs
):
    """The journal's 203/EXEC: a pass pointed the link at the new tip and died before it
    installed the tool again, so the link named the new tree and the tool the old one, and each
    later pass found the copy at green and did nothing more."""

    def killed(copy):
        raise Died

    monkeypatch.setattr(green, "_reinstall", killed)
    new = land(copied, "success")
    with pytest.raises(Died):
        copied.poll()
    assert at(copied.copy) == new

    monkeypatch.setattr(green, "_reinstall", lambda copy: installs.append(copy.resolve()) or "")
    said = copied.poll()
    assert installs == [green.trees(copied.copy) / new]
    line = f"green demo: the commands now run from {new[:12]}, in place of {copied.first[:12]}"
    assert line in said
    assert gates(copied) == []

    installs.clear()
    copied.poll()
    assert installs == []


def test_a_relink_that_is_refused_is_asked_again_by_the_next_pass(copied, monkeypatch):
    """A relink that is refused raised a condition and nothing owed it, so the layouts held the
    files of the last tip until an install by hand. The move keeps the relink owed until it is
    taken, and the next pass asks for it again, with no new tip."""
    asked, refuse = [], ["layout claude-code: Permission denied"]

    def relink(copy):
        asked.append(copy.resolve())
        return refuse

    monkeypatch.setattr(jinstall_green, "relink", relink)
    new = land(copied, "success")
    copied.poll()
    assert at(copied.copy) == new
    assert asked == [green.trees(copied.copy) / new]
    assert gates(copied) == [f"condition green: {green.UNLINKED}"]

    refuse = []
    copied.poll()
    assert asked == [green.trees(copied.copy) / new] * 2

    copied.poll()
    assert len(asked) == 2


def test_a_move_whose_tree_is_gone_goes_back_and_moves_again(copied, monkeypatch, installs):
    """A move that owes its install to a tree a hand removed leaves the link dangling: the pass
    puts it back on the tree it came from, says so, and moves to main's green tip again."""

    def killed(copy):
        raise Died

    monkeypatch.setattr(green, "_reinstall", killed)
    new = land(copied, "success")
    with pytest.raises(Died):
        copied.poll()
    tree = green.trees(copied.copy) / new
    shutil.rmtree(tree)

    monkeypatch.setattr(green, "_reinstall", lambda copy: installs.append(copy.resolve()) or "")
    copied.poll()
    assert gates(copied) == [f"condition green: {green.MOVE_FAILED}"]
    assert at(copied.copy) == new
    assert installs == [tree]
