"""`make check` runs the tests on a number of workers that it counts from the processors the run
may use: its cgroup's CPU quota where one is set, else the machine's. A desk takes a quarter of
them. A runner of GitHub's own, where every jstack CI job runs, takes one for each, and a
self-hosted runner takes one and a half for each processor of its quota. The count is never under
two. Each worker takes the next test when it finishes one, and the run
prints the 25 slowest tests. A test that passes leaves no directory under `/tmp`. A test that
fails keeps its own.

A runner is a run that GitHub Actions started. It says so with `GITHUB_ACTIONS=true`, and it says
whose machine it is on with `RUNNER_ENVIRONMENT`: `github-hosted` or `self-hosted`. A GitHub-hosted
runner runs nothing else, so it takes every processor. The tests that open a real browser carry the
marker `browser`. `make check` and `make check-fast` leave them out, and `make check-browser` runs
only them, one at a time. There, a runner with no browser fails them, and only a desk skips them. A
test module that opens a browser and lacks the marker fails here.

The workers are pytest-xdist's. Every worker collects the tests, and xdist stops the run when
two workers collect different ones. So a test's id must be the same in every process: an id
made from the clock differs between two workers that start in different seconds.

`make check-fast BASE=<rev>` is the check of a change. It runs the same lint, and then the test
files that `scripts/select_tests.py` names for the diff from that commit to the head. Where the
script says `all`, it runs `make check`. This module runs it in a copy of the repo, against a `uv`
that only records what it was asked.

A desk's share is also the test slots' count: every slot at once runs at most one desk worker
for each of the machine's processors. CI is not in that budget, since it runs on GitHub's machines.

This module is on `testing/macos-quick.txt`: its cases run the Makefile or a pytest's processes,
as a desk on a Mac does. The cases that do not, which no Mac does otherwise, and the cases that
collect the whole tree, which is collection and not a Mac's behavior, are
`test_check_command_off_mac.py`.
"""

import fcntl
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jgauge import sizes
from testing.paths import REPO

SET_BY_A_RUN = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "TEST_WORKERS", "GITHUB_ACTIONS", "CORES")
SET_BY_A_RUN += ("RUNNER_ENVIRONMENT", "CGROUP", "JUNIT", "SHARD", "PART")
SET_BY_A_RUN += ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "SELECTED", "JGAUGE_TEST_SLOT")
SCHEDULE = ["--dist", "worksteal", "--durations=25"]
UNLIMITED = {"CGROUP": "/nonexistent"}
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
    """The commands `make check` would run, one on each line, without running them.

    A run started as `make check TEST_WORKERS=2` passes that variable to every make under it. So
    this drops the variables a run sets (`SET_BY_A_RUN`) to get the Makefile's own count. Those
    include the variables that mark a run as a runner's run, so the count is a desk's unless `more`
    says otherwise. The cgroup has no `cpu.max` unless `more` names one. So the count is never the
    quota of the cgroup the suite itself runs under.

    """
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    env.update(UNLIMITED | more)
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
    """The environment without the variables that a pytest run sets or reads."""
    return {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}


def pytest_of(*args):
    """The words after `pytest` on the line of the pytest command `make -n <args>` would run."""
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "-n", *args],
        cwd=REPO,
        env=env | UNLIMITED,
        capture_output=True,
        text=True,
        check=True,
    )
    (line,) = [line for line in made.stdout.splitlines() if " pytest" in line]
    return shlex.split(line)[shlex.split(line).index("pytest") + 1 :]


def test_make_check_runs_the_tests_on_a_number_of_workers_set_in_one_place():
    assert pytest_of("check", "CORES=24") == ["-n", "6", *SCHEDULE, *LEAVES_OUT]
    assert pytest_of("check", "TEST_WORKERS=2") == ["-n", "2", *SCHEDULE, *LEAVES_OUT]
    reported = ["-n", "6", *SCHEDULE, *LEAVES_OUT, "--junitxml=/x/junit.xml"]
    assert pytest_of("check", "CORES=24", "JUNIT=/x/junit.xml") == reported


def workers(*args, **more):
    """The number of workers `make check` gives pytest."""
    (tests,) = [shlex.split(line) for line in check(*args, **more) if " pytest" in line]
    return int(tests[tests.index("-n") + 1])


def test_the_workers_are_counted_from_the_processors_of_the_machine_where_no_quota_is_set(
    tmp_path,
):
    """The machine's processors are what `getconf` says. Here a fake `getconf` on `PATH` says
    32."""
    (tmp_path / "getconf").write_text('#!/bin/sh\n[ "$1" = _NPROCESSORS_ONLN ] && echo 32\n')
    (tmp_path / "getconf").chmod(0o755)
    path = f"{tmp_path}:{os.environ['PATH']}"
    assert (workers(PATH=path), workers(PATH=path, GITHUB_ACTIONS="true")) == (8, 48)
    (tmp_path / "cpu.max").write_text("max 100000\n")
    assert workers(PATH=path, CGROUP=str(tmp_path)) == 8


def test_a_cgroup_quota_is_the_processors_a_run_counts_from_rounded_down_and_at_least_one(
    tmp_path,
):
    """`cpu.max` is the quota and the period in microseconds, as `docker --cpus` writes it."""
    runner = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"}
    counted = {}
    for quota in ("400000 100000", "250000 100000", "50000 100000", "1200000 100000"):
        (tmp_path / "cpu.max").write_text(quota + "\n")
        counted[quota] = (workers(CGROUP=str(tmp_path)), workers(CGROUP=str(tmp_path), **runner))
    assert counted == {
        "400000 100000": (2, 6),
        "250000 100000": (2, 3),
        "50000 100000": (2, 2),
        "1200000 100000": (3, 18),
    }
    assert workers("CORES=8", CGROUP=str(tmp_path), **runner) == 12


def test_the_quota_is_read_from_the_cgroup_the_run_is_in(tmp_path):
    """A run's cgroup is the directory under /sys/fs/cgroup that /proc/self/cgroup names: a
    container's own cgroup is `/`, and a command under `systemd-run --scope` gets the scope's
    cgroup. A system with no /proc/self/cgroup, such as macOS, has none, so no quota. The
    makefile that prints it is a file, since macOS's make, 3.81, has no `--eval`.
    """
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    printed = tmp_path / "cgroup.mk"
    printed.write_text("cgroup: ; @echo $(CGROUP)\n")
    made = subprocess.run(
        ["make", "-s", "-f", "Makefile", "-f", str(printed), "cgroup"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    named = Path("/proc/self/cgroup")
    if not named.exists():
        assert made.stdout == "\n"
        return
    (own,) = [line for line in named.read_text().splitlines() if line[:3] == "0::"]
    assert made.stdout == f"/sys/fs/cgroup{own[3:]}\n"


def test_a_runner_runs_one_and_a_half_workers_a_processor_a_desk_a_quarter_and_none_under_two():
    for cores, desk, runner in ((1, 2, 2), (4, 2, 6), (12, 3, 18), (24, 6, 36), (64, 16, 96)):
        counted = (workers(f"CORES={cores}"), workers(f"CORES={cores}", GITHUB_ACTIONS="true"))
        assert counted == (desk, runner), cores


def test_a_runner_of_githubs_own_takes_every_processor():
    hosted = ("GITHUB_ACTIONS=true", "RUNNER_ENVIRONMENT=github-hosted")
    assert "uv run pytest -n 4 " in check(*hosted, "CORES=4")[-1]
    ours = check("CORES=4", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="self-hosted")
    assert "uv run pytest -n 6 " in ours[-1]
    assert workers(CORES="4", GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted") == 4
    assert "uv run pytest -n 6 " in check("CORES=24")[-1]
    assert (workers(*hosted, "CORES=1"), workers(*hosted, "CORES=64")) == (2, 64)
    assert workers("RUNNER_ENVIRONMENT=github-hosted", "CORES=24") == 6


@pytest.mark.parametrize("cores", [1, 2, 4, 8, 12, 24, 64])
def test_every_full_slot_at_once_runs_at_most_one_desk_worker_a_processor(cores):
    """`make` counts the full slots from the Makefile's desk share, and `DESK_SHARE` is a copy of
    that share. Each worker uses 0.86 of a core, as measured on yelena on 2026-10-20. So when every
    slot runs at once, the slots keep at most 86% of the processors busy."""
    desk = workers(f"CORES={cores}")
    assert desk == sizes.desk_workers(cores)
    slots = sizes.derive(sizes.Name.TEST_SLOTS, sizes.Machine(cores, 1024))
    assert slots * desk <= max(cores, desk)


def test_a_count_of_processors_given_empty_is_read_as_two_and_the_tests_still_get_a_number():
    assert (workers("CORES="), workers(CORES="")) == (2, 2)
    assert "uv run pytest -n 4 " in check("TEST_WORKERS=4", GITHUB_ACTIONS="true")[-1]


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
    """The repo's config gives every test a time bound. Here the bound is 2 seconds, so a test that
    sleeps for 60 seconds fails with its name after 2 seconds, and the other test in the file still
    passes."""
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


TLC_IN_A_TEST = """
import os, subprocess, sys

sys.path.insert(0, os.environ["STATECHART_SCRIPTS"])
from statechart import tools


def test_tlc_runs():
    ran = tools.in_test_slot(["echo", "ran"])
    assert subprocess.run(ran, capture_output=True, text=True, timeout=10).stdout == "ran\\n"
"""


def test_on_a_runner_of_githubs_own_a_tlc_run_in_the_suite_waits_on_no_test_slot(tmp_path):
    """A runner of GitHub's own runs the suite alone, so a TLC run in it takes no jgauge slot:
    with every slot taken, it still runs at once. A macos-15 runner has 3 cores, which jgauge
    gives one slot, and each TLC run of the suite queued on it (nightly run 42059155018)."""
    (tmp_path / "test_scratch.py").write_text(TLC_IN_A_TEST)
    locks = tmp_path / "locks"
    locks.mkdir()
    env = {name: value for name, value in outside_a_run().items() if name not in SET_BY_A_RUN}
    env |= {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "TEST_SLOTS": "1"}
    env |= {"JGAUGE_LOCKS_DIR": str(locks), "PATH": f"{Path(sys.executable).parent}:{env['PATH']}"}
    env["STATECHART_SCRIPTS"] = str(REPO / "features/skill-library/skills/statechart/scripts")
    held = os.open(locks / "test-slot.1.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        ran = subprocess.run(
            ["make", "--no-print-directory", "test", "TEST_WORKERS=0"]
            + [f"TESTS={tmp_path / 'test_scratch.py'} --basetemp={tmp_path / 'base'}"],
            cwd=REPO,
            env=env | UNLIMITED,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        os.close(held)
    assert ran.returncode == 0 and "1 passed" in ran.stdout, ran.stdout + ran.stderr


def changed_copy(tmp_path, path, added="\n"):
    """A copy of the repo's files in a repo of its own, with two commits: the files as they are,
    then `added`, one blank line unless given, at the end of `path`. Return the copy, the `PATH`
    with the fake `uv` first, and the file where it records each command line it gets."""
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
                changed.write(added)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    bin.mkdir()
    asked = tmp_path / "asked"
    (bin / "uv").write_text(f'#!/bin/sh\necho "$*" >> {asked}\n')
    (bin / "uv").chmod(0o755)
    return copy, f"{bin}:{os.environ['PATH']}", asked


@pytest.fixture
def step_files(tmp_path, monkeypatch):
    """The step's own output and summary files, and the list of selected tests it keeps as an
    artifact, as a check job's step sets them around this suite. A test's `make check-fast` must
    leave them as they are: a line it added would be the step's, `selection=` there decides
    whether the job leaves the green tree marker, and the artifact names what the check ran."""
    files = [tmp_path / "output", tmp_path / "summary", tmp_path / "selected"]
    names = ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "SELECTED")
    for name, file in zip(names, files, strict=True):
        file.write_text("")
        monkeypatch.setenv(name, str(file))
    yield files
    assert [file.read_text() for file in files] == ["", "", ""]


def teed(path, kept):
    """Put a `python3` first on `path`, a `changed_copy` PATH, that writes what
    `scripts/select_tests.py` printed to `kept` as it passes it on: a test reads the selection
    `make check-fast` ran and runs no second one, since the real selector over a copy of the tree
    takes much of a test's time limit on a runner."""
    real = shutil.which("python3", path=os.environ["PATH"])
    shim = Path(path.split(":", 1)[0]) / "python3"
    shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = scripts/select_tests.py ]; then\n'
        f'    out=$({shlex.quote(real)} "$@") || exit $?\n'
        f"    printf '%s\\n' \"$out\" | tee {shlex.quote(str(kept))}\n"
        "    exit 0\n"
        "fi\n"
        f'exec {shlex.quote(real)} "$@"\n'
    )
    shim.chmod(0o755)


def check_fast(copy, path, *more):
    """What `uv` was asked by `make check-fast BASE=HEAD^1` in the copy, one call a line, with
    `more` on its command line."""
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "check-fast", "BASE=HEAD^1", "CORES=24", *more],
        cwd=copy,
        env=env | {"PATH": path},
        capture_output=True,
        text=True,
    )
    assert made.returncode == 0, made.stdout + made.stderr


def selected(copy):
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    ran = subprocess.run(
        [sys.executable, "scripts/select_tests.py", "HEAD^1", "HEAD"],
        cwd=copy,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.split()


SRC = sorted(str(path.relative_to(REPO)) for path in REPO.glob("features/*/src"))
LINT = [
    "run ruff check .",
    "run ruff format --check .",
    " ".join(["run pyrefly check --summary=none", *SRC]),
    "run python -W ignore::RuntimeWarning:runpy -m jbus.telemetry.firstload --check",
    "run repo-standard conform",
]
OFF = ["-m", "not", "browser"]


def test_check_fast_runs_the_lint_and_only_the_tests_the_change_reaches(tmp_path, step_files):
    copy, path, asked = changed_copy(tmp_path, "features/jdrift/src/jdrift/__init__.py")
    kept = tmp_path / "selector.out"
    teed(path, kept)
    check_fast(copy, path)
    *lint, run = asked.read_text().splitlines()
    pytest_line = " ".join(["run pytest -n 6", *SCHEDULE, *OFF])
    assert lint == LINT and run.startswith(f"{pytest_line} ")
    tests = run.removeprefix(pytest_line).split()
    assert (
        "features/jdrift/tests/test_drift.py" in tests
        and "features/jbus/tests/test_jbus_queue.py" not in tests
    )
    assert all(test.endswith(".py") and Path(copy, test).is_file() for test in tests), tests
    assert tests == kept.read_text().split()


PARTS = [
    ("guards", ["testing/tests/test_a.py", "testing/tests/test_b.py"], LINT),
    ("rest", ["testing/tests/test_c.py"], []),
    ("rest", [], None),
    ("rest", ["all"], []),
]


@pytest.mark.parametrize(("part", "tests", "lint"), PARTS)
def test_a_desk_part_of_check_fast_runs_only_its_own_tests_and_the_rest_no_lint(
    tmp_path, step_files, part, tests, lint
):
    """`PART=guards` is the lint and the guard tests, and `PART=rest` the other tests the change
    reaches, with no lint: the desk ran the lint with the guards. A rest of `all` is the whole
    suite, and an empty rest runs nothing. The selector here is a stand-in that prints `tests`
    for whatever part it is asked: the parts it prints are `test_select_tests.py`'s, and the real
    one, run twice over a copy of the tree, takes most of a test's time limit on a runner."""
    copy, path, asked = changed_copy(tmp_path, "features/jdrift/src/jdrift/__init__.py")
    argv = tmp_path / "argv"
    (copy / "scripts" / "select_tests.py").write_text(
        f"import sys\nopen({str(argv)!r}, 'w').write(' '.join(sys.argv[1:]))\n"
        f"print({chr(10).join(tests)!r})\n"
    )
    check_fast(copy, path, f"PART={part}")
    assert argv.read_text() == f"--part {part} HEAD^1 HEAD"
    run = " ".join(["run pytest -n 6", *SCHEDULE, *OFF, *(t for t in tests if t != "all")])
    said = asked.read_text().splitlines() if asked.exists() else []
    assert said == ([] if lint is None else [*lint, run])


def test_928s_807_line_module_fails_the_desks_guard_part_with_neither_0_nor_124(tmp_path):
    """#928's head, 969738d2d, grew `jbus/telemetry/records.py` to 807 lines, over the module cap,
    and its desk check ended 124: the short lane stopped it a third of the way into some 356
    selected files, before the size guard had run. The desk now runs `PART=guards` first, under a
    full slot, as a step that must pass, so the check fails on the guard with an exit that is
    neither 0 nor the lane's 124. The real selector picks the parts; the fake `uv` runs the size
    guard for real wherever a call names it, and a call that names a test the change reaches by
    import stands for the slow rest: it ends 124 at once, as the lane would stop it."""
    records = "features/jbus/src/jbus/telemetry/records/__init__.py"
    padding = "\n" * (807 - len((REPO / records).read_text().splitlines()))
    copy, path, asked = changed_copy(tmp_path, records, padding)
    guard = "features/repo-guards/tests/test_module_size.py"
    reached = "features/jbus/tests/test_jbus_telemetry.py"
    real = f"{sys.executable} -m pytest -q -p no:cacheprovider {guard}"
    (tmp_path / "bin" / "uv").write_text(
        f'#!/bin/sh\necho "$*" >> {asked}\n'
        f'case " $* " in *" {reached} "*) exit 124 ;; *" {guard} "*) exec {real} ;; esac\n'
    )
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    made = subprocess.run(
        ["make", "check-fast", "BASE=HEAD^1", "CORES=24", "PART=guards"],
        cwd=copy,
        env=env | {"PATH": path},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert made.returncode not in (0, 124), made.stdout
    assert f"{records}: has 807 lines, over 800" in made.stdout
    runs = [line for line in asked.read_text().splitlines() if line.startswith("run pytest")]
    assert len(runs) == 1 and f" {guard}" in runs[0] and reached not in runs[0], runs


def test_check_fast_is_make_check_when_the_change_is_one_the_whole_suite_rests_on(
    tmp_path, step_files
):
    copy, path, asked = changed_copy(tmp_path, "pyproject.toml")
    check_fast(copy, path)
    assert selected(copy) == ["all"]
    assert asked.read_text().splitlines() == [*LINT, " ".join(["run pytest -n 6", *SCHEDULE, *OFF])]


def test_check_fast_fails_on_a_base_that_is_not_a_commit_and_runs_nothing(tmp_path):
    copy, path, asked = changed_copy(tmp_path, "features/jdrift/src/jdrift/__init__.py")
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
