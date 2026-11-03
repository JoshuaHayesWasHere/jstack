"""Once jbus's config names the checkout `install.sh` runs from as a project, the install makes a
green copy of it and runs every command from that copy (`jinstall.green`), so a main that breaks
does not break jbus. A checkout jbus does not watch installs from itself, as before
(`test_install.py`)."""

import json
import os
import subprocess

import pytest

from jbus import green as copies
from jinstall import green
from jinstall.green import GreenCopy
from jinstall.machine import Machine, Ran
from test_install import User, laid, line_for
from testing.paths import REPO

MOVES = "which each jbus pass moves to main's green tip"
COMMIT = ["-c", "user.name=a", "-c", "user.email=a@example.test", "commit", "-q"]


def head(path):
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def watched(user, checkout):
    """jbus's config, with one project whose checkout is `checkout`."""
    user.write(
        user.jbus / "config.toml",
        f'server = "http://127.0.0.1:1"\n[[project]]\nname = "jstack"\n'
        f'checkout = "{checkout}"\nprojectId = "p"\n',
    )
    (user.jbus / "config.toml").chmod(0o600)


@pytest.fixture
def owner(tmp_path):
    user = User(tmp_path)
    watched(user, REPO)
    user.copy = user.home / ".local" / "share" / "jstack" / "green"
    return user


def test_the_install_of_a_watched_checkout_runs_every_command_from_its_green_copy(owner):
    code, said, err = owner.run_with_stderr()
    assert f"ok hard green copy {owner.copy} -> at {head(REPO)[:12]}, {MOVES}" in said, err
    assert copies.of(owner.copy) == REPO
    assert head(owner.copy) == head(REPO)
    assert owner.said(owner.uv_log) == [f"tool install --editable {owner.copy} --reinstall"]
    assert line_for(said, "hard commands jstack") == ["ok hard commands jstack"]
    for harness in ("claude-code", "codex", "cursor"):
        assert os.readlink(laid(owner.home, harness) / "source") == str(owner.copy)
    crew = laid(owner.home) / "skills" / "crew" / "SKILL.md"
    assert os.path.realpath(crew).startswith(str(owner.copy))
    assert (
        subprocess.run(
            ["git", "-C", str(REPO), "worktree", "list"], capture_output=True, text=True, check=True
        ).stdout.count(str(owner.copy))
        == 0
    )


def test_a_second_install_leaves_the_copy_where_jbus_moved_it(owner):
    owner.run()
    subprocess.run(["git", "-C", str(owner.copy), *COMMIT, "--allow-empty", "-m", "on"], check=True)
    moved = head(owner.copy)
    code, said, _ = owner.run_with_stderr()
    assert f"ok hard green copy {owner.copy} -> at {moved[:12]}, {MOVES}" in said
    assert head(owner.copy) == moved
    assert len(owner.said(owner.uv_log)) == 1


def test_check_says_the_copy_is_missing_and_makes_none(owner):
    code, said, _ = owner.run_with_stderr("--check")
    assert code == 1
    assert line_for(said, f"green copy {owner.copy}") == [
        f"missing hard green copy {owner.copy} -> install.sh makes it at main's last green tip"
    ]
    assert not owner.copy.exists()


def test_uninstall_removes_the_copy_with_the_tool(owner):
    owner.run()
    code, said, _ = owner.run_with_stderr("--uninstall")
    assert f"removed green copy {owner.copy}" in said
    assert not owner.copy.exists()
    assert owner.said(owner.uv_log)[-1] == "tool uninstall jstack"


def test_a_checkout_jbus_does_not_watch_gets_no_copy(tmp_path):
    user = User(tmp_path)
    code, said, _ = user.run_with_stderr()
    assert not line_for(said, "green copy")
    assert user.said(user.uv_log) == [f"tool install --editable {REPO} --reinstall"]


@pytest.fixture
def small(tmp_path, monkeypatch):
    """A checkout of two commits that jbus watches, and the machine of a HOME beside it."""
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    for message in ("first", "second"):
        subprocess.run(
            ["git", "-C", str(checkout), *COMMIT, "--allow-empty", "-m", message], check=True
        )
    user = User(tmp_path)
    watched(user, checkout)
    monkeypatch.setenv("JBUS_STATE_DIR", str(user.home / ".local" / "state" / "jbus"))
    env = {"PATH": os.environ["PATH"], "JBUS_CONFIG_DIR": str(user.jbus)}

    def run(args):
        done = subprocess.run(list(args), capture_output=True, text=True)
        return Ran(done.returncode, done.stdout)

    machine = Machine(checkout, user.home, env, run, tmp_path / "account")
    return green.attach(machine), checkout


def test_a_new_copy_starts_at_main_s_green_tip_as_jbus_keeps_it(small):
    machine, checkout = small
    first = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    state = machine.home / ".local" / "state" / "jbus" / "jstack"
    state.mkdir(parents=True)
    (state / "main.json").write_text(json.dumps({"main": first, "check": "green", "green": first}))
    assert green.tip(machine) == first
    assert green.make(machine) == ""
    assert head(machine.green) == first


def test_with_no_green_tip_kept_a_new_copy_starts_at_the_checkout_s_commit(small):
    machine, checkout = small
    assert green.tip(machine) == head(checkout)


def test_jinstall_run_from_the_copy_acts_for_the_checkout_it_was_made_from(small):
    machine, checkout = small
    assert machine.green == machine.home / ".local" / "share" / "jstack" / "green"
    assert green.make(machine) == ""
    from_copy = green.attach(
        Machine(machine.green, machine.home, machine.env, machine.run, machine.account)
    )
    assert (from_copy.checkout, from_copy.green) == (checkout, machine.green)
    assert from_copy.source == machine.green


def test_the_copy_of_another_checkout_is_not_written_over(small, tmp_path):
    machine, _ = small
    other = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    subprocess.run(["git", "-C", str(other), *COMMIT, "--allow-empty", "-m", "o"], check=True)
    assert copies.make(other, machine.green, head(other)) == ""
    found = GreenCopy(machine.green).probe(machine)
    assert (found.detail, found.replaceable) == (f"the green copy of {other}", False)
    assert GreenCopy(machine.green).drop(machine).removed == ()
