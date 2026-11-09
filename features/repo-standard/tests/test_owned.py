"""A caller's own inputs to the shared check are the repo's: conform reads no drift of them, and
upgrade keeps them.

A repo whose runner has no Docker sets `browser-channel: chrome` beside its `runner:`, and needs
no `local:` entry for its check.yml to keep it (rt-caller-inputs-not-drift)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from repo_standard import VERSION, owned
from repo_standard.cli import main
from testing.paths import REPO

FEATURE = REPO / "features" / "repo-standard"
CALLER = owned.CALLER
DRIFT = "warn a-file-a-version-owns-is-that-versions-copy"
SKELETON = (FEATURE / "skeleton" / CALLER).read_text()
OWN = "      runner: winnifred-ephemeral\n      browser-channel: chrome\n"
MINE = SKELETON.replace("      runner: ubuntu-24.04\n", OWN)


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    subprocess.run(command, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A repo made from this version's skeleton and python-uv adapter, whose caller runs on a
    runner of its own with Chrome and no Docker."""
    root = tmp_path / "repo"
    shutil.copytree(FEATURE / "skeleton", root)
    shutil.copytree(FEATURE / "adapters" / "python-uv", root, dirs_exist_ok=True)
    (root / CALLER).write_text(MINE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    return root


def drift(root, capsys):
    main(["conform", "--root", str(root), "--upstream", ""])
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith(DRIFT)]


def test_a_caller_with_its_own_runner_and_browser_channel_conforms(repo, capsys):
    assert "browser-channel: chrome" in (repo / CALLER).read_text()
    assert drift(repo, capsys) == []


def test_a_caller_that_changes_an_input_of_the_versions_still_drifts(repo, capsys):
    """The control: the call's `command` is the version's, and an edit of it is drift."""
    caller = repo / CALLER
    caller.write_text(caller.read_text().replace("command: 'make check'", "command: 'make x'"))
    assert [line.split(": ")[1] for line in drift(repo, capsys)] == [CALLER]


def test_upgrade_writes_the_versions_caller_with_the_repos_own_inputs_kept(repo, capsys):
    caller = repo / CALLER
    caller.write_text(caller.read_text().replace('cron: "0 8 * * *"', 'cron: "0 9 * * *"'))
    assert main(["upgrade", "--to", str(VERSION), "--root", str(repo), "--upstream", ""]) == 0
    assert f"wrote {CALLER}" in capsys.readouterr().out.splitlines()
    assert caller.read_text() == MINE
    assert drift(repo, capsys) == []


def test_upgrade_writes_the_versions_caller_whole_over_a_call_with_no_with(repo, capsys):
    """A caller whose call of the shared check has no `with:` has no inputs of its own to keep."""
    caller = repo / CALLER
    block = "    with:\n" + OWN + "      command: 'make check'\n"
    caller.write_text(caller.read_text().replace(block, ""))
    assert "with:" not in caller.read_text()
    assert main(["upgrade", "--to", str(VERSION), "--root", str(repo), "--upstream", ""]) == 0
    assert caller.read_text() == SKELETON
