"""The crew skill's proof block runs the tests a branch changes at its head, then laid over its
merge-base's code, and prints the `Proved:` line `jmerge` reads (`ready.short_on_proved`). A
test that fails without the change proves it; one that passes at the base as well proves nothing,
and the line says so with the base's exit 0. A branch that changes no test gets no run.

The tests run the block in a real repo whose `origin/main` is the base, with a `uv` on PATH that
runs pytest on this interpreter, takes the slot by running the command, and syncs nothing."""

import subprocess
import sys

import pytest

from crew_helpers import block, git
from jbriefs import proved

UV = f"""#!/bin/bash
case " $* " in
*" jgauge test-slot "*)
    while [ "$1" != -- ]; do shift; done
    shift
    exec "$@"
    ;;
*" sync "*) exit 0 ;;
*" run pytest "*)
    shift 2
    exec {sys.executable} -m pytest "$@"
    ;;
esac
exit 64
"""
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
        (tree / name).write_text(text)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "the change")
    return git(tree, "rev-parse", "HEAD")


def proof(tree):
    script = block("Do the task", "Proved: ").replace("<slug>", "a-task")
    script = script.replace("<thread id>", "mcp:thread-1")
    home = tree.parent / "home"
    ran = subprocess.run(
        ["bash", "-c", script],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": f"{tree.parent / 'stub'}:/usr/bin:/bin",
            "HOME": str(tree.parent),
            "H": str(home),
            "T": str(tree.parent / "templates"),
        },
    )
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
