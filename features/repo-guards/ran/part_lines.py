"""A pytest plugin that records, as a part of CI's check runs its tests, which lines of the
feature code the branch changes each test file runs, so the guard of `test_new_lines_run` reads
them once the parts end and no part runs a test twice for it.

`make test NEW_LINES_PART=<folder>` loads it, with `NEW_LINES_BASE` the base the branch is read
from (HEAD^1 on GitHub's merge). Each process that loads it measures, from its own start, only
the Python files under a feature's `src/` or `scripts/` that the diff from the base changes, so
code the branch leaves alone costs next to nothing: coverage runs on `sys.monitoring`, which stops
calling it for a function outside those files after its first call. A line's context is the test
file that ran it (its path from the repo's root), set as each test starts; a line that ran while
no test did, at collection or as a conftest imported its module, has the empty context. A
process a test starts is measured too, through coverage's `.pth` file and
`COVERAGE_PROCESS_START`, with the context of that test's file from `NEW_LINES_TEST`.

`sys.monitoring` records a line once and then stops watching it, so the plugin asks it to watch
every line again when the test file changes: a line one test file ran is then also recorded for
the next file that runs it.

A process that runs tests drops `NEW_LINES_PART` and `NEW_LINES_BASE` from its environment as
its first test starts, after pytest-xdist has started the workers that need them, so a make or a
pytest a test runs records nothing of its own.

It writes to the folder coverage's data, folded into `data`, and `tests.<pid>`, the test files the
process ran, one a line. A part where the diff changes no such file measures nothing and writes
nothing.
"""

import os
import subprocess
import sys
from pathlib import Path

import coverage
import pytest
from data_files import ended

FOLDER = os.environ.get("NEW_LINES_PART")
BASE = os.environ.get("NEW_LINES_BASE", "HEAD^1")
CODE = ("features/*/src/*.py", "features/*/scripts/*.py")


def changed() -> list[str]:
    """The Python files of a feature's code the diff from `BASE` changes, as absolute paths."""
    names = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=d", BASE, "--", *CODE],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [str(Path(name).resolve()) for name in names]


def started(folder: Path, files: list[str]) -> coverage.Coverage:
    """Coverage of `files`, started, with its settings in a file the processes tests start read."""
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / f"coveragerc.{os.getpid()}"
    config.write_text(
        "[run]\ncore = sysmon\nparallel = true\n"
        "context = ${NEW_LINES_TEST-}\n"
        "disable_warnings = no-sysmon-context, no-data-collected, module-not-measured\n"
        f"data_file = {folder / 'data'}\n"
        f"include =\n{''.join(f'    {path}\n' for path in files)}"
    )
    measured = coverage.Coverage(config_file=str(config))
    measured.start()
    os.environ["COVERAGE_PROCESS_START"] = str(config)
    return measured


FILES = changed() if FOLDER else []
MEASURED = started(Path(FOLDER), FILES) if FOLDER and FILES else None
RAN: set[str] = set()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item) -> None:
    os.environ.pop("NEW_LINES_PART", None)
    os.environ.pop("NEW_LINES_BASE", None)
    if MEASURED is None:
        return
    name = item.path.relative_to(item.config.rootpath).as_posix()
    RAN.add(name)
    if os.environ.get("NEW_LINES_TEST") != name:
        os.environ["NEW_LINES_TEST"] = name
        MEASURED.switch_context(name)
        sys.monitoring.restart_events()


@pytest.hookimpl(wrapper=True)
def pytest_sessionfinish(session: pytest.Session):
    """Save what this process measured. The process that started the run, once its workers
    have ended (pytest-xdist ends them in its own hook, which this one wraps), folds into one
    file, `data`, every process's data file whose writer has ended: a part's tests start
    hundreds of Python processes, each with a file of its own (532 files, 28 MB, in one part of
    1083 tests), and the one file keeps every line and its contexts in about 70 kB to upload.
    A process a test started and left running is still writing its file, so the fold leaves it
    out, and its lines with it."""
    yield
    if MEASURED is None:
        return
    MEASURED.stop()
    MEASURED.save()
    (Path(FOLDER) / f"tests.{os.getpid()}").write_text("".join(f"{name}\n" for name in RAN))
    if hasattr(session.config, "workerinput"):
        return
    if files := ended(Path(FOLDER)):
        folded = coverage.Coverage(config_file=MEASURED.config.config_file, data_suffix=False)
        folded.combine(data_paths=files, keep=False)
        folded.save()
