import json
import os
import subprocess
from pathlib import Path

import pytest

from jgauge import cli, whole
from test_machine_sizes import fake_proc
from test_room import BIN

WHOLE = [
    ["make", "check"],
    ["make", "check-fast", "BASE=origin/main"],
    ["make", "test"],
    ["uv", "run", "pytest", "-q", "-n", "auto"],
    ["python3", "-m", "pytest", "-k", "tests"],
]


@pytest.fixture
def repo(tmp_path):
    """A repo whose check selects its tests, whose make targets and pytest each leave a mark that
    they ran, on a machine of its own with no slot taken."""
    top = tmp_path / "repo"
    (top / ".git").mkdir(parents=True)
    (top / "scripts").mkdir()
    (top / "scripts" / "select_tests.py").write_text("")
    (top / "tests").mkdir()
    (top / "tests" / "test_one.py").write_text("")
    (top / "Makefile").write_text("check check-fast test:\n\ttouch ran\n", encoding="utf-8")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name in ("pytest", "python3", "uv"):
        (bin_ / name).write_text("#!/bin/sh\ntouch ran\n")
        (bin_ / name).chmod(0o755)
    home = tmp_path / "home"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "PROC": str(fake_proc(tmp_path / "proc", 24, 62)),
        "TMPFS": str(tmp_path),
    }
    for name in ("TEST_SLOTS", "XDG_CONFIG_HOME", "JGAUGE_TEST_SLOT", "PART", "TESTS"):
        env.pop(name, None)

    def run(*args, at=top):
        return subprocess.run(
            [str(BIN / "jgauge"), "test-slot", *args],
            cwd=at,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    run.top = top
    return run


@pytest.mark.parametrize("command", WHOLE, ids=" ".join)
@pytest.mark.parametrize("lane", [["--short"], []], ids=["short", "full"])
def test_a_thread_in_a_selecting_repo_is_refused_a_whole_suite_and_told_the_touched_check(
    repo, command, lane, monkeypatch, capsys
):
    monkeypatch.chdir(repo.top)
    for name in ("PART", "TESTS"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["test-slot", *lane, "--thread", "t1", "--", *command]) == 2
    said = capsys.readouterr().err
    assert "runs the whole suite" in said
    assert whole.TOUCHED in said
    assert not (repo.top / "ran").exists()


@pytest.mark.parametrize(
    "command",
    [
        ["make", "test", "TESTS=tests/test_one.py"],
        ["make", "check-fast", "BASE=origin/main", "PART=touched"],
        ["uv", "run", "pytest", "-q", "-n", "2", "tests/test_one.py::test_a"],
        ["uv", "run", "pytest", "tests"],
    ],
    ids=" ".join,
)
def test_a_thread_in_a_selecting_repo_runs_one_file_or_the_touched_check(repo, command):
    ran = repo("--short", "--thread", "t1", "--", *command)
    assert ran.returncode == 0, ran.stderr
    assert (repo.top / "ran").exists()


@pytest.mark.parametrize("command", [["echo", "ran"], ["sh", "-c", "make check"]], ids=" ".join)
def test_a_command_that_is_no_make_or_pytest_is_no_whole_suite(repo, command):
    assert whole.refusal(command, repo.top, {}) == ""


def test_a_whole_suite_runs_with_no_thread_or_in_a_repo_that_selects_nothing(repo):
    assert repo("--", "make", "check").returncode == 0
    (repo.top / "ran").unlink()
    (repo.top / "scripts" / "select_tests.py").unlink()
    assert whole.refusal(["make", "check"], repo.top / "tests", {}) == ""
    assert repo("--thread", "t1", "--", "make", "check").returncode == 0
    assert (repo.top / "ran").exists()


def test_a_run_of_the_repo_leaves_no_holder_in_the_lock_dir_of_the_pytest_run(repo):
    """A holder left in the pytest run's lock dir is owed a wake that a later test's jbus pass
    tries to tell (lab-replay-holder-leak): the repo's runs keep their slots to its own machine."""
    holders = Path(os.environ["JGAUGE_LOCKS_DIR"]) / "test-slot-holders.json"

    def ids():
        return {h["id"] for h in json.loads(holders.read_text())} if holders.exists() else set()

    before = ids()
    ran = repo("--short", "--thread", "t1", "--", "make", "test", "TESTS=tests/test_one.py")
    assert ran.returncode == 0, ran.stderr
    assert ids() == before
