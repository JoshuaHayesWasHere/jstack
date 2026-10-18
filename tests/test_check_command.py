"""`make check` runs the tests on a number of workers counted from the machine's processors,
fewer on a runner of this machine than at a desk and never under two, and a test that passes
leaves no directory under `/tmp`. A test that fails keeps its own.

A runner is a run GitHub Actions started, which says so with `GITHUB_ACTIONS=true`, and says
whose machine it is on with `RUNNER_ENVIRONMENT`: `github-hosted` or `self-hosted`. One of
GitHub's own runs nothing else, so it takes every processor. The tests that open a real
browser carry the marker `browser`: `make check` and `make check-fast` leave them out, and
`make check-browser` runs only them, one at a time. There a runner fails them for want of a
browser, and only a desk skips them. A test module that opens a browser and lacks the marker
fails here.

The workers are pytest-xdist's, which has every worker collect the tests and stops the run
when two of them differ. So a test's id must be the same in every process: one made from the
clock differs between two workers that start in different seconds.

`make check-fast BASE=<rev>` is the check of a change: the same lint, and the test files
`scripts/select_tests.py` names for the diff from that commit to the head, or `make check`
where it says `all`. It is run here in a copy of the repo, against a `uv` that only says
what it was asked.

The machine's budget is one sum: the test slots times a desk's workers, plus the runners
times a runner's. It is worked out here from the slot default and from what `make` prints.
The runners are three, and no file of the repo counts them: their units are the machine's.
"""

import os
import re
import shlex
import shutil
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
LEAVES_OUT = ["-m", "not browser"]
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


def collected(*more):
    """The id of every test, as a new process collects them, `more` being pytest's options."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *more],
        cwd=REPO,
        env=outside_a_run(),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in ran.stdout.splitlines() if "::" in line]


def pytest_of(*args):
    """The words after `pytest` on the line of the pytest command `make -n <args>` would run."""
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "-n", *args], cwd=REPO, env=env, capture_output=True, text=True, check=True
    )
    (line,) = [line for line in made.stdout.splitlines() if " pytest" in line]
    return shlex.split(line)[shlex.split(line).index("pytest") + 1 :]


def test_make_check_runs_the_tests_on_a_number_of_workers_set_in_one_place():
    assert pytest_of("check", "CORES=12") == ["-n", "4", *LEAVES_OUT]
    assert pytest_of("check", "TEST_WORKERS=2") == ["-n", "2", *LEAVES_OUT]


def workers(*args, **more):
    """The number of workers `make check` gives pytest."""
    (tests,) = [shlex.split(line) for line in check(*args, **more) if " pytest" in line]
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
    assert "uv run pytest -n 4" in check(*hosted, "CORES=4")[-1]
    ours = check("CORES=12", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="self-hosted")
    assert "uv run pytest -n 2" in ours[-1]
    assert workers(CORES="4", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted") == 4
    assert "uv run pytest -n 4" in check("CORES=12")[-1]
    assert (workers(*hosted, "CORES=1"), workers(*hosted, "CORES=64")) == (2, 64)
    assert workers("RUNNER_ENVIRONMENT=github-hosted", "CORES=12") == 4


def test_every_slot_and_every_runner_at_once_ask_twelve_processors_for_fourteen_workers():
    desk = workers("CORES=12")
    runner = workers("CORES=12", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="self-hosted")
    assert slot.DEFAULT * desk + RUNNERS * runner <= 14


def test_a_count_of_processors_given_empty_is_read_as_two_and_the_tests_still_get_a_number():
    assert (workers("CORES="), workers(CORES="")) == (2, 2)
    assert "uv run pytest -n 4" in check("TEST_WORKERS=4", GITHUB_ACTIONS="true")[-1]


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
    """A run of `make check-browser`'s pytest command on a machine with no browser on `PATH`
    and none named in `JSTACK_TEST_BROWSER`: how it ended, and what it printed."""
    named = ("GITHUB_ACTIONS", "JSTACK_TEST_BROWSER")
    env = {name: value for name, value in outside_a_run().items() if name not in named}
    (tmp_path / "bin").mkdir(exist_ok=True)
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
        + ["--basetemp", str(tmp_path / "base"), *pytest_of("check-browser")],
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


def changed_copy(tmp_path, path):
    """A copy of the repo's files in a repo of its own, with two commits: the files as they
    are, then one line added to `path`. Gives the copy and where `uv` writes what it was asked.
    """
    copy, bin = tmp_path / "copy", tmp_path / "bin"
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    for name in filter(None, listed):
        if (REPO / name).is_file():
            (copy / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, copy / name)
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(copy)]
    subprocess.run([*git, "init", "-q"], check=True)
    for message in ("base", "change"):
        if message == "change":
            with open(copy / path, "a") as changed:
                changed.write("\n")
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    bin.mkdir()
    asked = tmp_path / "asked"
    (bin / "uv").write_text(f'#!/bin/sh\necho "$*" >> {asked}\n')
    (bin / "uv").chmod(0o755)
    return copy, f"{bin}:{os.environ['PATH']}", asked


def check_fast(copy, path):
    """What `uv` was asked by `make check-fast BASE=HEAD^1` in the copy, one call a line."""
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "check-fast", "BASE=HEAD^1", "CORES=12"],
        cwd=copy,
        env=env | {"PATH": path},
        capture_output=True,
        text=True,
    )
    assert made.returncode == 0, made.stdout + made.stderr


def selected(copy):
    ran = subprocess.run(
        [sys.executable, "scripts/select_tests.py", "HEAD^1", "HEAD"],
        cwd=copy,
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.split()


LINT = ["run ruff check .", "run ruff format --check ."]
OFF = ["-m", "not", "browser"]


def test_check_fast_runs_the_lint_and_only_the_tests_the_change_reaches(tmp_path):
    copy, path, asked = changed_copy(tmp_path, "src/jdrift/__init__.py")
    check_fast(copy, path)
    tests = selected(copy)
    assert "tests/test_drift.py" in tests and "tests/test_jbus.py" not in tests
    assert asked.read_text().splitlines() == [*LINT, " ".join(["run pytest -n 4", *OFF, *tests])]


def test_check_fast_is_make_check_when_the_change_is_one_the_whole_suite_rests_on(tmp_path):
    copy, path, asked = changed_copy(tmp_path, "pyproject.toml")
    check_fast(copy, path)
    assert selected(copy) == ["all"]
    assert asked.read_text().splitlines() == [*LINT, " ".join(["run pytest -n 4", *OFF])]


def test_check_fast_fails_on_a_base_that_is_not_a_commit_and_runs_nothing(tmp_path):
    copy, path, asked = changed_copy(tmp_path, "src/jdrift/__init__.py")
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "check-fast", "BASE=nowhere"],
        cwd=copy,
        env=env | {"PATH": path},
        capture_output=True,
        text=True,
    )
    assert made.returncode != 0 and "git diff failed" in made.stderr
    assert not asked.exists()


def test_make_check_browser_runs_the_marked_tests_alone_one_at_a_time_and_no_lint():
    assert pytest_of("check-browser") == ["-m", "browser"]
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "-n", "check-browser"], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert made.stdout.splitlines() == ["uv run pytest -m browser"]


def test_the_browser_tests_are_the_whole_of_one_module_and_the_other_run_leaves_them_out():
    everything, marked, others = collected(), collected("-m", "browser"), collected(*LEAVES_OUT)
    assert marked and others
    assert sorted(marked + others) == sorted(everything)
    assert {test.split("::")[0] for test in marked} == {"tests/test_jbus_view_page.py"}


def test_a_marker_the_config_does_not_list_is_an_error_and_not_a_typo_that_passes(tmp_path):
    (tmp_path / "test_scratch.py").write_text(
        "import pytest\n\n\n@pytest.mark.brower\ndef test_a():\n    pass\n"
    )
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
        + ["-c", str(REPO / "pyproject.toml"), "--rootdir", str(tmp_path)]
        + ["--basetemp", str(tmp_path / "base"), str(tmp_path / "test_scratch.py")],
        cwd=tmp_path,
        env=outside_a_run(),
        capture_output=True,
        text=True,
    )
    assert ran.returncode != 0 and "'brower' not found in `markers`" in ran.stdout + ran.stderr


OPENS = re.compile(r"--headles[s]|browser[.]lock")


def browser_files(directory):
    """The test files of the directory that start a browser or take the browser lock, and
    those pytest collects under `-m browser`, which is what the marker is for."""
    opening = {
        path.name for path in sorted(directory.glob("test_*.py")) if OPENS.search(path.read_text())
    }
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + ["-c", str(REPO / "pyproject.toml"), "--rootdir", str(directory), "-m", "browser"]
        + [str(directory)],
        cwd=directory,
        env=outside_a_run(),
        capture_output=True,
        text=True,
    )
    assert ran.returncode in (0, 5), ran.stdout + ran.stderr
    ids = [line.split("::")[0] for line in ran.stdout.splitlines() if "::" in line]
    return opening, {Path(one).name for one in ids}


def test_a_test_module_that_opens_a_browser_without_the_marker_is_found(tmp_path):
    flag = "--head" + "less"
    opens = f'import pytest\n\nCOMMAND = "{flag}"\n\n\ndef test_a():\n    pass\n'
    marker = "import pytest\n\npytestmark = pytest.mark.browser\n"
    (tmp_path / "test_marked.py").write_text(opens.replace("import pytest\n", marker, 1))
    (tmp_path / "test_unmarked.py").write_text(opens)
    (tmp_path / "test_quiet.py").write_text("def test_c():\n    pass\n")
    opening, marked = browser_files(tmp_path)
    assert (sorted(opening), sorted(marked)) == (
        ["test_marked.py", "test_unmarked.py"],
        ["test_marked.py"],
    )


def test_every_test_module_that_opens_a_browser_carries_the_marker():
    opening, marked = browser_files(REPO / "tests")
    assert "test_jbus_view_page.py" in opening
    assert sorted(opening - marked) == []
