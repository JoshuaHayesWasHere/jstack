"""A crew whose CI check failed, in a repo whose check selects its tests, runs the test files
CI's failed jobs name, each alone in the short lane, and never the whole suite."""

import os
import subprocess

import test_room as room
from crew_helpers import Failed, block, git, run
from test_machine_sizes import fake_proc
from testing.layouts import assembled

LOG = (
    "check 3 of 8\tmake test\t2026-11-10T01:31:28Z FAILED tests/test_a.py::test_x - assert 1 == 2\n"
    "check 3 of 8\tmake test\t2026-11-10T01:31:29Z ERROR tests/test_b.py - ImportError\n"
    "check 5 of 8\tmake test\t2026-11-10T01:31:30Z FAILED tests/test_gone.py::test_y - boom\n"
)
GH = """#!/bin/sh
case "$1 $2" in
    "run view") echo "$*" >> "$STUB/views"; cat "$STUB/log-$3.txt" ;;
    *) exec "$REAL_GH" "$@" ;;
esac
"""
MAKE = """#!/bin/sh
echo "$* $JGAUGE_TEST_SLOT" >> "$STUB/make.log"
case "$*" in *test_b.py*) exit 1 ;; esac
"""


def files_block(tmp_path, selects=True):
    """Run the block of "The failed files" in a pull request's worktree whose failed check is
    job 2 of run 5, with the log above, and return what it printed and the runs of `make`."""
    failed = Failed(tmp_path)
    if selects:
        (failed.work / "scripts").mkdir()
        (failed.work / "scripts" / "select_tests.py").write_text("")
    (failed.work / "tests").mkdir()
    for name in ("test_a.py", "test_b.py"):
        (failed.work / "tests" / name).write_text("")
    git(failed.work, "add", "-A")
    git(failed.work, "commit", "-qm", "tests")
    failed.push([run("SUCCESS", 1), run("FAILURE", 2)])
    shim = tmp_path / "shim"
    shim.mkdir()
    for name, text in (("gh", GH), ("make", MAKE)):
        (shim / name).write_text(text)
        (shim / name).chmod(0o755)
    room.uv(shim)
    (failed.stub / "log-5.txt").write_text(LOG)
    script = block("Stay on the pull request", "--log-failed").replace("<thread id>", "t1")
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PROC": str(fake_proc(tmp_path / "proc", 24, 62)),
        "PATH": f"{shim}:{room.BIN}:{failed.stub}:{os.environ['PATH']}",
        "REAL_GH": str(failed.stub / "gh"),
        "STUB": str(failed.stub),
        "H": str(failed.state),
        "T": str(assembled() / "templates"),
    }
    for name in ("TEST_SLOTS", "JGAUGE_TEST_SLOT", "XDG_CONFIG_HOME"):
        env.pop(name, None)
    said = subprocess.run(
        ["bash", "-c", script], cwd=failed.work, env=env, capture_output=True, text=True
    )
    made = failed.stub / "make.log"
    return said.stdout.splitlines(), made.read_text().splitlines() if made.exists() else []


def test_each_file_the_failed_jobs_name_runs_alone_in_the_short_lane(tmp_path):
    said, made = files_block(tmp_path)
    assert made == ["test TESTS=tests/test_a.py short", "test TESTS=tests/test_b.py short"]
    assert "tests/test_gone.py: not in this worktree, so not run" in said
    assert said[-1] == "failed files: exit 1"


def test_a_repo_that_selects_no_tests_runs_nothing_more(tmp_path):
    said, made = files_block(tmp_path, selects=False)
    assert made == []
    assert said[-1].startswith("none: ")
