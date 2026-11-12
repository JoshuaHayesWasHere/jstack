"""The record of what the install made, `~/.local/state/jstack/created`, against a stop at any
point: after an install that stopped anywhere, and after any later install, uninstall's sweep
leaves HOME as it was before jstack touched it, the record's own folder and the levels above it
included."""

import os

import pytest

from jinstall.machine import Machine, Ran


class Stop(BaseException):
    """The install's process dies here: nothing after it runs, and no handler sees it."""


def a_machine(tmp_path, fresh):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    if not fresh:
        (home / ".local" / "state").mkdir(parents=True)
    return Machine(None, home, {}, lambda args: Ran(None, ""), tmp_path / "account", tmp_path)


def listing(machine):
    return sorted(str(path.relative_to(machine.home)) for path in machine.home.rglob("*"))


def stopped_after(monkeypatch, n, step):
    """Run `step`, and stop its process just after its `n`th mkdir."""
    real, made = os.mkdir, []

    def mkdir(path, *args, **kwargs):
        real(path, *args, **kwargs)
        made.append(path)
        if len(made) == n:
            raise Stop

    with monkeypatch.context() as patched:
        patched.setattr(os, "mkdir", mkdir)
        try:
            step()
        except Stop:
            return True
    return False


SHAPES = pytest.mark.parametrize("fresh", [True, False], ids=["fresh HOME", "HOME has state"])


@SHAPES
@pytest.mark.parametrize("n", [1, 2, 3])
def test_an_install_stopped_after_a_mkdir_leaves_nothing_once_uninstalled(
    tmp_path, monkeypatch, fresh, n
):
    machine = a_machine(tmp_path, fresh)
    before = listing(machine)
    stopped_after(monkeypatch, n, lambda: machine.make_dirs(machine.home / ".config" / "jstack"))
    machine.sweep()
    assert listing(machine) == before


@SHAPES
@pytest.mark.parametrize("n", [1, 2, 3])
def test_a_later_install_records_what_a_stopped_one_made(tmp_path, monkeypatch, fresh, n):
    machine = a_machine(tmp_path, fresh)
    before = listing(machine)
    made = machine.home / ".config" / "jstack"
    stopped_after(monkeypatch, n, lambda: machine.make_dirs(made))
    machine.make_dirs(made)
    assert made.is_dir()
    machine.sweep()
    assert listing(machine) == before


@SHAPES
def test_a_seeded_file_alone_leaves_no_record_folder_once_uninstalled(tmp_path, fresh):
    machine = a_machine(tmp_path, fresh)
    before = listing(machine)
    seeded = machine.home / ".config" / "seeded.toml"
    machine.seed(seeded, "x = 1\n", 0o600)
    assert machine.unseed(seeded) is True
    machine.sweep()
    assert listing(machine) == before
