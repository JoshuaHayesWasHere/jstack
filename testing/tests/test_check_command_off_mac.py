"""The cases of `make check`'s tests that test nothing a Mac does otherwise and read no more
than their own files: the Makefile's comment lines, the job's time bound in check.yml, the step
files and the select job's step on `ubuntu-24.04`, the browser fixture's skip, a marker the config
does not list, and the finder of a browser test with no marker, on files of their own. They are
not on `testing/macos-quick.txt`, so Linux runs them and the Mac does not. The cases that run
the Makefile or a pytest's processes, as a desk on a Mac does, and those that read the whole
tree, are `test_check_command.py`, which the Mac runs."""

import os
import re
import subprocess
import sys
import tomllib

from test_check_command import (
    SET_BY_A_RUN,
    browser_files,
    changed_copy,
    outside_a_run,
    pytest_of,
    step_files,
)
from testing.paths import REPO

__all__ = ["step_files"]


def test_every_comment_line_of_the_makefile_fits_the_repos_line_length():
    length = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["ruff"]["line-length"]
    lines = (REPO / "Makefile").read_text().splitlines()
    long = [n for n, line in enumerate(lines, 1) if line.startswith("#") and len(line) > length]
    assert long == []


def test_the_bound_of_a_test_is_well_inside_the_jobs_limit():
    """A hang fails its test, and the run reaches its summary, long before GitHub cancels the
    job."""
    bound = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    text = (REPO / ".github/workflows/check.yml").read_text()
    job = re.search(r"\n  check-shard:\n(?:    .*\n|\s*\n)*?    timeout-minutes: (\d+)", text)
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


def test_no_test_writes_to_the_step_output_of_the_job_that_runs_it(tmp_path, step_files):
    """A test of `select_tests.py` runs the script as a job's step would, and the job's step files
    are in the environment of every test: the suite's fixtures keep them out of each test."""
    one = "testing/tests/test_select_tests.py::"
    one += "test_a_changed_module_selects_each_test_that_imports_it_directly_or_by_a_chain"
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", one],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0 and "1 passed" in ran.stdout, ran.stdout[-2000:]


def test_a_selection_pytest_cannot_collect_fails_the_select_step_and_still_keeps_its_list(
    tmp_path,
):
    """The job `select` fails where pytest cannot collect the selection, and the run that fails
    there is the one that most needs the list of what was selected: the step still writes it to
    `SELECTED`, which the job keeps as an artifact, and to its summary."""
    broken = "features/jdrift/tests/test_drift.py"
    copy, _, _ = changed_copy(tmp_path, broken, "\nraise SystemExit('no collect')\n")
    files = {name: tmp_path / name.lower() for name in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}
    files["SELECTED"] = tmp_path / "selected"
    env = {name: value for name, value in os.environ.items() if name not in SET_BY_A_RUN}
    ran = subprocess.run(
        [sys.executable, "scripts/select_tests.py", "--parts", "2", "HEAD^1", "HEAD"],
        cwd=copy,
        env=env | {name: str(file) for name, file in files.items()},
        capture_output=True,
        text=True,
    )
    assert ran.returncode != 0 and "pytest could not collect the selection" in ran.stderr
    kept = files["SELECTED"].read_text().splitlines() if files["SELECTED"].exists() else []
    assert any(line.startswith(f"{broken} ") for line in kept), kept
    assert all((copy / line.split()[0]).is_file() for line in kept), kept
    assert "\n".join(kept) in files["GITHUB_STEP_SUMMARY"].read_text()


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


def test_a_test_module_in_a_folder_that_opens_a_browser_through_a_module_it_imports_is_found(
    tmp_path,
):
    flag = "--head" + "less"
    (tmp_path / "conftest.py").write_text("")
    (tmp_path / "area").mkdir()
    (tmp_path / "area" / "opener.py").write_text(f'COMMAND = "{flag}"\n')
    (tmp_path / "area" / "test_through.py").write_text(
        "from area.opener import COMMAND\n\n\ndef test_d():\n    assert COMMAND\n"
    )
    (tmp_path / "area" / "test_quiet.py").write_text("def test_e():\n    pass\n")
    opening, marked = browser_files(tmp_path)
    assert (sorted(opening), sorted(marked)) == (["test_through.py"], [])
