"""An agent's shell capped at a full slot's workers, `jgauge cap-shell PID`, against a stand-in
for `/sys/fs/cgroup` and `/proc`: the shell joins the leaf of `jgauge-shell` under its own
cgroup, a shell that cannot be capped runs as before and hears nothing, and a take from a capped
shell is made beside the shell's cgroup with its own cap and its own CPU."""

import json
import os

import pytest

from jgauge import cli, slot, slotlog

SCOPE = "user.slice/app.slice/t3code-claude-1.scope"
SHELL = f"{SCOPE}/{slotlog.SHELL}/{slotlog.LEAF}"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A cgroup tree with the agent's scope, and a `/proc` whose processes are in the cgroups
    `where` puts them in; returns the scope and `where`."""
    monkeypatch.setattr(slotlog, "CGROUPS", tmp_path / "cgroups")
    monkeypatch.setattr(slotlog, "PROCS", tmp_path / "proc")
    scope = tmp_path / "cgroups" / SCOPE
    scope.mkdir(parents=True)
    (scope / "cgroup.subtree_control").write_text("")

    def where(pid: int | str, cgroup: str) -> None:
        (tmp_path / "proc" / str(pid)).mkdir(parents=True, exist_ok=True)
        (tmp_path / "proc" / str(pid) / "cgroup").write_text(cgroup)

    return scope, where


def cap(pid: int, capsys) -> str:
    """Run `jgauge cap-shell PID`, as the env file's line does, and return what it printed."""
    assert cli.main(["cap-shell", str(pid)]) == 0
    said = capsys.readouterr()
    return said.out + said.err


def test_a_shell_joins_the_leaf_of_its_scope_s_capped_shell_cgroup_on_every_command(tree, capsys):
    scope, where = tree
    where(41, f"0::/{SCOPE}\n")

    assert cap(41, capsys) == ""

    shell = scope / slotlog.SHELL
    workers = slot.workers(slot.full(1))
    assert (shell / "cpu.max").read_text().split() == [str(workers * 100_000), "100000"]
    assert (scope / "cgroup.subtree_control").read_text() == "+cpu"
    assert (shell / slotlog.LEAF / "cgroup.procs").read_text() == "41"
    assert not (shell / slotlog.LEAF / "cpu.max").exists()

    where(42, f"0::/{SCOPE}\n")
    assert cap(42, capsys) == ""
    assert (shell / slotlog.LEAF / "cgroup.procs").read_text() == "42"


@pytest.mark.parametrize(
    "cgroup",
    [f"0::/{SHELL}\n", f"0::/{SCOPE}/{slotlog.PREFIX}ab12/{slotlog.LEAF}\n"],
    ids=["in the shell's cgroup", "in a take's"],
)
def test_a_shell_already_in_a_cgroup_of_jgauge_s_stays_where_it_is(tree, capsys, cgroup):
    scope, where = tree
    (scope / f"{slotlog.PREFIX}ab12" / slotlog.LEAF).mkdir(parents=True)
    where(41, cgroup)

    assert cap(41, capsys) == ""

    assert not list(scope.rglob(f"{slotlog.SHELL}/{slotlog.LEAF}/{slotlog.SHELL}"))
    assert not (scope / f"{slotlog.PREFIX}ab12" / slotlog.LEAF / slotlog.SHELL).exists()


def test_a_shell_that_cannot_be_capped_runs_as_before_and_hears_nothing(tree, capsys):
    """cgroup v1 gives a line for each hierarchy; a process with no `/proc` entry is macOS's
    case or one gone; a cgroup the user may not write is one whose directory is not there to
    make the shell's cgroup in."""
    scope, where = tree
    where(41, "12:cpu,cpuacct:/user.slice\n0::/user.slice\n")
    where(43, "0::/user.slice/session-2.scope\n")
    (slotlog.CGROUPS / "user.slice").chmod(0o500)
    try:
        for pid in (41, 42, 43):
            assert cap(pid, capsys) == ""
    finally:
        (slotlog.CGROUPS / "user.slice").chmod(0o700)

    assert not list(slotlog.CGROUPS.rglob(slotlog.SHELL))


def test_a_take_from_a_capped_shell_is_capped_beside_it_and_counts_its_own_cpu(
    tree, tmp_path, monkeypatch
):
    """Beside and not under: under the shell's cgroup the take would share the shell's cores
    with whatever the agent runs outside the slot, and its slot would run below the workers it
    is sized for. The holder goes back to the shell's leaf at the release."""
    scope, where = tree
    (scope / slotlog.SHELL / slotlog.LEAF).mkdir(parents=True)
    where("self", f"0::/{SHELL}\n")
    monkeypatch.setattr(slotlog, "DRAIN_SECONDS", 0.1)
    log = slotlog.path(tmp_path / "locks")

    taken = slotlog.take(log, "full", 1, 4, "", ["make", "check"], 0, workers=3)
    (own,) = scope.glob(f"{slotlog.PREFIX}*")
    assert (own / "cpu.max").read_text().split() == ["300000", "100000"]
    assert not list((scope / slotlog.SHELL).rglob(f"{slotlog.PREFIX}*"))
    (own / "cpu.stat").write_text("user_usec 2500000\nsystem_usec 500000\n")
    slotlog.release(taken, 0)

    release = json.loads(log.read_text().splitlines()[-1])
    assert (release["cpu_user"], release["cpu_system"], release["left"]) == (2.5, 0.5, 0)
    assert (scope / slotlog.SHELL / slotlog.LEAF / "cgroup.procs").read_text() == str(os.getpid())
