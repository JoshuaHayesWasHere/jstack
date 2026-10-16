"""`make check` runs the tests on a number of workers counted from the machine's processors,
fewer on a runner of this machine than at a desk and never under two, and a test that passes
leaves no directory under `/tmp`. A test that fails keeps its own.

A runner is a run GitHub Actions started, which says so with `GITHUB_ACTIONS=true`, and says
whose machine it is on with `RUNNER_ENVIRONMENT`: `github-hosted` or `self-hosted`. One of
GitHub's own runs nothing else, so it takes every processor. A runner also runs the browser
tests or fails: only a desk skips them for want of a browser.

The workers are pytest-xdist's, which has every worker collect the tests and stops the run
when two of them differ. So a test's id must be the same in every process: one made from the
clock differs between two workers that start in different seconds.

The machine's budget is one sum: the test slots times a desk's workers, plus the runners
times a runner's. It is worked out here from the slot default and from what `make` prints.
The runners are three, and no file of the repo counts them: their units are the machine's.
"""

import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from jgauge import slot

REPO = Path(__file__).parent.parent
SET_BY_A_RUN = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "TEST_WORKERS", "GITHUB_ACTIONS", "CORES")
SET_BY_A_RUN += ("RUNNER_ENVIRONMENT",)
RUNNERS = 3
SCRATCH = """
def test_a_passes(tmp_path):
    (tmp_path / "written").write_text("x")


def test_b_fails(tmp_path):
    (tmp_path / "written").write_text("x")
    assert 1 == 2
"""
HANGS = """
import time


def test_a_hangs():
    time.sleep(60)


def test_b_passes():
    pass
"""


def check(*args, **more):
    """The commands `make check` would run, one a line, without running them.

    A run started as `make check TEST_WORKERS=2` hands that on to every make under it, so the
    count asked about here is the Makefile's own only with those variables taken out. What
    says the run is a runner's goes with them: the count is a desk's unless `more` says so.
    """
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    env.update(more)
    made = subprocess.run(
        ["make", "-n", "check", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return made.stdout.splitlines()


def outside_a_run():
    """The environment with what a pytest run sets, or is told by, taken out."""
    return {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}


def collected():
    """The id of every test, as a new process collects them."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO,
        env=outside_a_run(),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in ran.stdout.splitlines() if "::" in line]


def test_make_check_runs_the_tests_on_a_number_of_workers_set_in_one_place():
    (tests,) = [line.split() for line in check("CORES=12") if " pytest" in line]
    assert tests == ["uv", "run", "pytest", "-n", "4"]
    assert "uv run pytest -n 2" in check("TEST_WORKERS=2")


def workers(*args, **more):
    """The number of workers `make check` gives pytest."""
    (tests,) = [line.split() for line in check(*args, **more) if " pytest" in line]
    return int(tests[tests.index("-n") + 1])


def test_the_workers_are_counted_from_the_processors_of_the_machine_the_run_is_on(tmp_path):
    """The machine's processors are what `getconf` says, here one on `PATH` that says 30."""
    (tmp_path / "getconf").write_text('#!/bin/sh\n[ "$1" = _NPROCESSORS_ONLN ] && echo 30\n')
    (tmp_path / "getconf").chmod(0o755)
    path = f"{tmp_path}:{os.environ['PATH']}"
    assert (workers(PATH=path), workers(PATH=path, GITHUB_ACTIONS="true")) == (10, 5)


def test_a_runner_runs_the_tests_on_fewer_workers_than_a_desk_and_neither_on_under_two():
    for cores, desk, runner in ((1, 2, 2), (4, 2, 2), (12, 4, 2), (64, 21, 10)):
        counted = (workers(f"CORES={cores}"), workers(f"CORES={cores}", GITHUB_ACTIONS="true"))
        assert counted == (desk, runner), cores


def test_a_runner_of_githubs_own_takes_every_processor_and_one_of_this_machine_a_sixth():
    hosted = ("GITHUB_ACTIONS=true", "RUNNER_ENVIRONMENT=github-hosted")
    assert "uv run pytest -n 4" in check(*hosted, "CORES=4")
    ours = check("CORES=12", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="self-hosted")
    assert "uv run pytest -n 2" in ours
    assert workers(CORES="4", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted") == 4
    assert "uv run pytest -n 4" in check("CORES=12")
    assert (workers(*hosted, "CORES=1"), workers(*hosted, "CORES=64")) == (2, 64)
    assert workers("RUNNER_ENVIRONMENT=github-hosted", "CORES=12") == 4


def test_every_slot_and_every_runner_at_once_ask_twelve_processors_for_fourteen_workers():
    desk = workers("CORES=12")
    runner = workers("CORES=12", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="self-hosted")
    assert slot.DEFAULT * desk + RUNNERS * runner <= 14


def test_a_count_of_processors_given_empty_is_read_as_two_and_the_tests_still_get_a_number():
    assert (workers("CORES="), workers(CORES="")) == (2, 2)
    assert "uv run pytest -n 4" in check("TEST_WORKERS=4", GITHUB_ACTIONS="true")


def test_a_passed_test_leaves_no_directory_behind_and_a_failed_one_keeps_its_own(tmp_path):
    (tmp_path / "test_scratch.py").write_text(SCRATCH)
    base = tmp_path / "base"
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-n", "2", "-p", "no:cacheprovider"]
        + ["-c", str(REPO / "pyproject.toml"), "--rootdir", str(tmp_path)]
        + ["--basetemp", str(base), str(tmp_path / "test_scratch.py")],
        cwd=tmp_path,
        env=outside_a_run(),
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 1 and "1 failed, 1 passed" in ran.stdout
    kept = sorted(path.name for path in base.glob("*/*") if not path.is_symlink())
    assert kept == ["test_b_fails0"]


def test_a_test_that_hangs_fails_by_name_inside_its_bound_and_the_run_goes_on(tmp_path):
    """The repo's config gives every test a bound. Here it is 2 s, so a test that sleeps 60 s
    fails with its name after 2, and the test beside it still passes."""
    (tmp_path / "test_scratch.py").write_text(HANGS)
    started = time.monotonic()
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-n", "2", "-p", "no:cacheprovider"]
        + ["-c", str(REPO / "pyproject.toml"), "--rootdir", str(tmp_path), "-o", "timeout=2"]
        + ["--basetemp", str(tmp_path / "base"), str(tmp_path / "test_scratch.py")],
        cwd=tmp_path,
        env=outside_a_run(),
        capture_output=True,
        text=True,
    )
    took = time.monotonic() - started
    assert ran.returncode == 1 and "1 failed, 1 passed" in ran.stdout, ran.stdout + ran.stderr
    assert "FAILED test_scratch.py::test_a_hangs" in ran.stdout
    assert "Timeout (>2.0s)" in ran.stdout
    assert took < 30


def test_the_bound_of_a_test_is_well_inside_the_jobs_limit():
    """A hang fails its test, and the run reaches its summary, long before the job is cut."""
    bound = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    job = re.search(r"timeout-minutes: (\d+)", (REPO / ".github/workflows/check.yml").read_text())
    assert 0 < int(bound["timeout"]) * 4 <= int(job[1]) * 60


def browser_tests(tmp_path, **more):
    """A run of the browser tests on a machine with no browser on `PATH` and none named in
    `JSTACK_TEST_BROWSER`: how it ended, and what it printed."""
    named = ("GITHUB_ACTIONS", "JSTACK_TEST_BROWSER")
    env = {name: value for name, value in outside_a_run().items() if name not in named}
    (tmp_path / "bin").mkdir(exist_ok=True)
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
        + ["--basetemp", str(tmp_path / "base"), "tests/test_jbus_view_page.py"],
        cwd=REPO,
        env=env | {"PATH": str(tmp_path / "bin")} | more,
        capture_output=True,
        text=True,
    )
    return ran.returncode, ran.stdout + ran.stderr


def test_with_no_browser_a_desk_skips_the_browser_tests_and_a_runner_fails_every_one(tmp_path):
    passed, desk = browser_tests(tmp_path)
    failed, runner = browser_tests(tmp_path, GITHUB_ACTIONS="true")
    skipped, errors = re.search(r"(\d+) skipped", desk), re.search(r"(\d+) errors", runner)
    assert passed == 0 and skipped and " passed" not in desk, desk
    assert failed == 1 and errors and errors[1] == skipped[1] and int(errors[1]) > 1, runner
    said = re.findall(r"^E +Failed: no chromium on PATH", runner, re.M)
    assert len(said) == int(errors[1]), runner


def test_every_test_has_the_same_id_a_second_later():
    first = collected()
    second = int(time.time())
    while int(time.time()) == second:
        time.sleep(0.05)
    assert collected() == first and first
