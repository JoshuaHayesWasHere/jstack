"""The crew skill's proof block runs the tests a branch changes at its head, then laid over its
merge-base's code, and prints the `Proved:` line `jmerge` reads (`ready.short_on_proved`). A
test that fails without the change proves it; one that passes at the base as well proves nothing,
and the line says so with the base's exit 0. A branch that changes no test gets no run.

The tests run the block in a real repo whose `origin/main` is the base, on macOS's tools
(`bsd_tools`), with a `uv` on PATH that runs pytest on this interpreter, takes the slot by running
the command, and syncs nothing. Each run leaves `git worktree list` as it found it, whether its
tests pass, fail or are cut off."""

import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

from crew_helpers import block, git
from jbriefs import proved
from test_blocks_command_grep import UGREP
from test_portable_shell import bsd_tools

UV = f"""#!/bin/bash
case " $* " in
*" jgauge test-slot "*)
    while [ "$1" != -- ]; do shift; done
    shift
    if [ -n "$LIMIT" ]; then exec {shutil.which("timeout")} "$LIMIT" "$@"; fi
    exec "$@"
    ;;
*" sync "*) exit 0 ;;
*" run python "*)
    if [ -n "$NO_XDIST" ]; then exit 1; fi
    shift 2
    exec {sys.executable} "$@"
    ;;
*" run pytest "*)
    if [ -n "$STALL" ]; then
        : > "$STALL"
        sleep 60
    fi
    if [ -n "$SLOW" ]; then sleep "$SLOW"; fi
    shift 2
    echo "$*" >> "$TMPDIR/pytest-args"
    exec {sys.executable} -m pytest "$@"
    ;;
esac
exit 64
"""
"""`uv` as the block calls it. A test-slot run is stopped at `LIMIT` seconds, exit 124, as the
short lane stops one at its limit; each pytest run takes `SLOW` seconds more, and `NO_XDIST`
stands for a repo whose venv has no pytest-xdist."""
BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
OLD_TEST = "from calc import add\n\n\ndef test_zero():\n    assert add(0, 0) == 0\n"
FAILS_AT_BASE = OLD_TEST + "\n\ndef test_two():\n    assert add(2, 2) == 4\n"
PASSES_AT_BASE = OLD_TEST + "\n\ndef test_still_zero():\n    assert add(1, 0) == 1\n"
RESULT = "# a-task: a task\n\n## Result\nStatus: done\n"


@pytest.fixture
def repo(tmp_path):
    """A repo whose base commit has a buggy `add` and a test that misses the bug, with
    `origin/main` at that commit, and a home whose brief has a Result."""
    tree = tmp_path / "repo"
    tree.mkdir()
    git(tree, "init", "-q", "-b", "main")
    git(tree, "config", "user.email", "crew@example.test")
    git(tree, "config", "user.name", "crew")
    (tree / "calc.py").write_text(BUGGY)
    (tree / "tests").mkdir()
    (tree / "tests" / "test_calc.py").write_text(OLD_TEST)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "base")
    git(tree, "update-ref", "refs/remotes/origin/main", "HEAD")
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "uv").write_text(UV)
    (stub / "uv").chmod(0o755)
    (tmp_path / "home" / "tasks").mkdir(parents=True)
    (tmp_path / "home" / "tasks" / "a-task.md").write_text(RESULT)
    return tree


def commit(tree, files):
    for name, text in files.items():
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_text(text)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "the change")
    return git(tree, "rev-parse", "HEAD")


def script():
    return (
        block("Do the task", "Proved: ")
        .replace("<slug>", "a-task")
        .replace("<thread id>", "mcp:thread-1")
    )


def environ(tree, **more):
    return {
        "PATH": f"{tree.parent / 'stub'}:{bsd_tools(tree.parent / 'bsd')}",
        "HOME": str(tree.parent),
        "H": str(tree.parent / "home"),
        "T": str(tree.parent / "templates"),
        "TMPDIR": str(tree.parent),
        "PYTEST_XDIST_AUTO_NUM_WORKERS": "2",
        **more,
    }


def worktrees(tree):
    return git(tree, "worktree", "list", "--porcelain")


def proof(tree, shell="", **more):
    before = worktrees(tree)
    ran = subprocess.run(
        ["bash", "-c", shell + script()],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=60,
        env=environ(tree, **more),
    )
    assert worktrees(tree) == before
    home = tree.parent / "home"
    return ran.stdout, proved.proved((home / "tasks" / "a-task.md").read_text())


def test_a_test_that_fails_without_the_fix_is_proved(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo)
    assert "head exit 0: 2 passed" in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_test_that_passes_at_the_base_too_is_written_with_its_exit_0(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": PASSES_AT_BASE})
    _, line = proof(repo)
    assert (line.base_exit, line.head_exit) == (0, 0)


def test_a_test_of_a_name_the_base_lacks_fails_at_the_base_and_is_no_collection_error(repo):
    added = "from calc import times\n\n\ndef test_times():\n    assert times(2, 3) == 6\n"
    times = "\n\ndef times(a, b):\n    return a * b\n"
    commit(repo, {"calc.py": FIXED + times, "tests/test_times.py": added})
    _, line = proof(repo)
    assert (line.tests, line.base_exit, line.head_exit) == (("tests/test_times.py",), 1, 0)


def test_a_change_with_no_test_runs_nothing_and_writes_no_line(repo):
    commit(repo, {"README.md": "how\n"})
    said, line = proof(repo)
    assert said.startswith("no test changed: the Result says Proved: none, <kind>")
    assert line is None


def test_a_test_that_fails_at_the_head_too_leaves_the_worktree_list_as_it_was(repo):
    broken = OLD_TEST + "\n\ndef test_three():\n    assert add(1, 1) == 3\n"
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": broken})
    said, line = proof(repo)
    assert "head exit 1: 1 failed, 1 passed" in said
    assert (line.base_exit, line.head_exit) == (1, 1)


def test_a_run_cut_off_mid_test_leaves_the_worktree_list_as_it_was(repo):
    """A thread's harness kills a call that runs past its time limit, and the user can stop one:
    nothing after the kill runs, so the block makes nothing it would have to undo."""
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    before = worktrees(repo)
    stalled = repo.parent / "stalled"
    running = subprocess.Popen(
        ["bash", "-c", script()],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environ(repo, STALL=str(stalled)),
        start_new_session=True,
    )
    try:
        waited = time.monotonic() + 30
        while not stalled.exists():
            assert running.poll() is None and time.monotonic() < waited
            time.sleep(0.05)
    finally:
        os.killpg(running.pid, signal.SIGKILL)
        running.wait()
    assert worktrees(repo) == before


def test_a_test_that_reads_git_runs_at_the_base_in_a_repo_of_its_own(repo):
    """A test the change lays over the base may run git in its tree, as one that lists the
    tracked files does: at the base it finds a repository at the base's commit, so it fails
    there only for the change and not for want of a `.git`."""
    reads = (
        "import subprocess\n\n\ndef test_tracked():\n"
        "    said = subprocess.run(\n"
        "        ['git', 'ls-files'], capture_output=True, text=True, check=True\n"
        "    )\n"
        "    assert 'calc.py' in said.stdout.split()\n"
    )
    commit(repo, {"calc.py": FIXED, "tests/test_git.py": reads})
    said, line = proof(repo)
    assert "base exit 0: 1 passed" in said
    assert (line.base_exit, line.head_exit) == (0, 0)


def test_a_branch_that_changes_only_tests_runs_them_at_the_head_alone(repo):
    """A test made faster changes no code: the base's code is the head's own, so the tests pass
    there too and a base run proves nothing. The block runs them at the head and says so."""
    faster = OLD_TEST + "\n\ndef test_one():\n    assert add(1, 0) == 1\n"
    head = commit(repo, {"tests/test_calc.py": faster, "tests/conftest.py": ""})
    said, line = proof(repo)
    assert "tests only: every file the branch changes is a test" in said
    assert "head exit 0: 2 passed" in said
    assert "base exit" not in said
    assert f"Proved: tests/test_calc.py head exit 0 at {head}, tests only\n" in said
    assert line == proved.Proved(("tests/test_calc.py",), head_exit=0, head=head, tests_only=True)


def test_a_branch_that_changes_tests_with_docs_and_config_runs_them_at_the_head_alone(repo):
    """A removal of tests with the doc that named them changes no code either: `jmerge` takes
    the `tests only` line where every other file is of a `jbriefs.proved.EXEMPT` kind, so the
    block prints it for such a branch."""
    head = commit(
        repo,
        {
            "tests/test_calc.py": PASSES_AT_BASE,
            "README.md": "how\n",
            "docs/guide": "why\n",
            "pyproject.toml": "[project]\n",
            ".github/workflows/ci.yml": "on: push\n",
            ".gitignore": "*.pyc\n",
        },
    )
    said, line = proof(repo)
    assert "tests only: every file the branch changes is a test" in said
    assert "base exit" not in said
    assert f"Proved: tests/test_calc.py head exit 0 at {head}, tests only\n" in said
    assert line == proved.Proved(("tests/test_calc.py",), head_exit=0, head=head, tests_only=True)


def test_a_branch_that_changes_a_test_docs_and_any_other_file_runs_it_at_the_base_too(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(
        repo, {"tests/test_calc.py": PASSES_AT_BASE, "README.md": "how\n", "util.py": ""}
    )
    said, line = proof(repo)
    assert "tests only" not in said
    assert "base exit 0: 2 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 0, base, 0, head)


def test_a_change_to_source_and_tests_runs_at_the_base_where_grep_is_claude_codes_ugrep(repo):
    """In a Claude Code agent shell `grep` is a function that runs its embedded ugrep, which
    answered `grep -qvE` with no line kept where grep kept one: the block said "tests only" for
    a change to `calc.py`. `UGREP` stands in for it."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, shell=UGREP)
    assert "tests only" not in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_slow_test_file_is_proved_where_the_head_and_the_base_each_fit_the_lane(repo):
    """A test file that takes over half the short lane's limit, as
    `testing/tests/test_select_tests.py` does, fits it at the head and at the base, but not both
    in one run: each runs in a slot of its own, and the block still writes one `Proved:` line."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, LIMIT="7", SLOW="4")
    assert "no proof" not in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_the_head_and_the_base_run_on_pytests_workers_where_the_repo_has_them(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    proof(repo)
    runs = (repo.parent / "pytest-args").read_text().splitlines()
    assert len(runs) == 2
    assert all("-n auto" in run for run in runs)


def test_a_repo_without_pytest_xdist_is_proved_on_one_process(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, NO_XDIST="1")
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)
    runs = (repo.parent / "pytest-args").read_text().splitlines()
    assert not any("-n " in run for run in runs)
