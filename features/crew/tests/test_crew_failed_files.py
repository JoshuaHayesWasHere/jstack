"""A crew whose CI check failed, in a repo whose check selects its tests, runs the test files
CI's failed jobs name, each alone in the short lane, and never the whole suite."""

import os
import shutil
import subprocess

import pytest

import test_room as room
from crew_helpers import Failed, block, git, run
from jgauge.slot import SHORT_LIMIT_SECONDS
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
POSIX_SED = """#!/bin/sh
exec {sed} --posix "$@" 2> /dev/null
"""
"""GNU sed held to POSIX, as macOS's BSD sed is, so the block's sed is read on Linux as on a Mac."""
MAKE = """#!/bin/sh
echo "$* $JGAUGE_TEST_SLOT" >> "$STUB/make.log"
case "$*" in *test_b.py*) exit 1 ;; esac
"""


def files_block(tmp_path, selects=True, kept="", times=""):
    """Run the block of "The failed files" in a pull request's worktree whose failed check is
    job 2 of run 5, with the log above, and return what it printed and the runs of `make`.
    `kept` is what the worktree's `crew-failed-files` held before, from an earlier red, and
    `times` what the repo's `crew-check-times` held, from the check blocks before."""
    failed = Failed(tmp_path)
    if kept:
        (failed.git_dir / "crew-failed-files").write_text(kept)
    if selects:
        (failed.work / "scripts").mkdir()
        (failed.work / "scripts" / "select_tests.py").write_text("")
    (failed.work / "tests").mkdir()
    for name in ("test_a.py", "test_b.py"):
        (failed.work / "tests" / name).write_text("")
    git(failed.work, "add", "-A")
    git(failed.work, "commit", "-qm", "tests")
    if times:
        common = failed.work / git(failed.work, "rev-parse", "--git-common-dir")
        (common / "crew-check-times").write_text(times)
    failed.push([run("SUCCESS", 1), run("FAILURE", 2)])
    shim = tmp_path / "shim"
    shim.mkdir()
    for name, text in (("gh", GH), ("make", MAKE)):
        (shim / name).write_text(text)
        (shim / name).chmod(0o755)
    sed = shutil.which("sed")
    if "GNU" in subprocess.run([sed, "--version"], capture_output=True, text=True).stdout:
        (shim / "sed").write_text(POSIX_SED.format(sed=sed))
        (shim / "sed").chmod(0o755)
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


def test_the_failed_files_are_kept_for_the_check(tmp_path):
    """The block keeps each name it read, beside `crew-check-steps`, where the check block of
    "Do the task" takes them as steps, and an earlier red's name not passed since stays."""
    files_block(tmp_path, kept="tests/test_old.py\n")
    work = tmp_path / "trees" / "a-task"
    kept = work / git(work, "rev-parse", "--git-path", "crew-failed-files")
    assert kept.read_text().splitlines() == [
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_gone.py",
        "tests/test_old.py",
    ]


def test_a_file_measured_over_the_short_lanes_limit_runs_in_a_full_slot_first(tmp_path):
    """A failed file whose last time in the repo's `crew-check-times` is the short lane's limit
    or more, as a check block keeps a file the lane stopped alone, runs in a full slot with no
    short attempt; one measured under it before, as later, runs in the short lane."""
    said, made = files_block(
        tmp_path, times="tests/test_a.py 300.0\ntests/test_b.py 120\ntests/test_b.py 9.5\n"
    )
    assert made == ["test TESTS=tests/test_a.py full", "test TESTS=tests/test_b.py short"]
    assert "tests/test_a.py: exit 0, full lane" in said


@pytest.mark.parametrize(
    ("took", "lane"),
    [(SHORT_LIMIT_SECONDS, "full"), (SHORT_LIMIT_SECONDS - 0.1, "short")],
    ids=["at jgauge's limit", "under it"],
)
def test_the_full_slot_first_rule_goes_by_jgauges_short_limit(tmp_path, took, lane):
    """A limit jgauge moved and this block did not would send a file the lane can finish to a
    full slot, or one it cannot to a 124: the block's line is jgauge's `SHORT_LIMIT_SECONDS`."""
    said, made = files_block(tmp_path, times=f"tests/test_a.py {took}\n")
    assert made[0] == f"test TESTS=tests/test_a.py {lane}", made
