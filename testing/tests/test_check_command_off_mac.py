"""The cases of `make check`'s tests that test nothing a Mac does otherwise: the Makefile's
comment lines, the job's time bound in check.yml, the step files, the browser fixture's skip, a
marker the config does not list, and the finder of a browser test with no marker, on files of
their own. With them are the cases that collect the whole tree: the same id a second later, the
browser tests' places, and the marker on every module that opens a browser. Collection is the
same on a Mac as on Linux, so they are not on `testing/macos-quick.txt` either: Linux runs them
and the Mac does not. The cases that run the Makefile or a pytest's processes, as a desk on a Mac
does, are `test_check_command.py`, which the Mac runs."""

import re
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_check_command import (
    LEAVES_OUT,
    outside_a_run,
    pytest_of,
    step_files,
)
from testing.paths import REPO

__all__ = ["step_files"]

PAGE = REPO / "features" / "jbus" / "tests" / "view" / "page"
SITE = REPO / "features" / "skill-library" / "tests" / "test_statechart_site.py"


def collected(*more):
    """The id of every test, as a new process collects them. `more` holds pytest's options."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *more],
        cwd=REPO,
        env=outside_a_run(),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in ran.stdout.splitlines() if "::" in line]


def test_every_test_has_the_same_id_a_second_later():
    first = collected()
    second = int(time.time())
    while int(time.time()) == second:
        time.sleep(0.05)
    assert collected() == first and first


def test_the_browser_tests_are_two_known_places_and_the_other_run_leaves_them_out():
    """The browser tests are those of `jbus view`'s page, in their folder, and the test that
    opens the statechart site's page at a desk's and a phone's width."""
    with ThreadPoolExecutor() as pool:
        runs = pool.map(lambda more: collected(*more), [[], ["-m", "browser"], LEAVES_OUT])
        everything, marked, others = runs
    assert marked and others
    assert sorted(marked + others) == sorted(everything)
    assert {test.split("::")[0] for test in marked} == {
        path.relative_to(REPO).as_posix() for path in [*PAGE.glob("test_*.py"), SITE]
    }


OPENS = re.compile(r"--headles[s]|browser[.]lock")
IMPORTS = re.compile(r"^(?:from|import) ([\w.]+)", re.M)


def browser_files(directory):
    """Two sets of test files under the directory. The first holds the files that start a browser or
    take the browser lock, directly or through a module of the directory that they import. The
    second holds the files that pytest collects under `-m browser`, the selection the marker is for.
    """
    texts = {path: path.read_text() for path in sorted(directory.rglob("*.py"))}
    opens = {
        ".".join(path.relative_to(directory).with_suffix("").parts)
        for path, text in texts.items()
        if OPENS.search(text)
    }
    opening = {
        path.name
        for path, text in texts.items()
        if path.name.startswith("test_")
        and (OPENS.search(text) or set(IMPORTS.findall(text)) & opens)
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


def test_every_test_module_that_opens_a_browser_carries_the_marker():
    tests = REPO / "features" / "jbus" / "tests"
    opening, marked = browser_files(tests)
    page = {path.name for path in (tests / "view" / "page").glob("test_*.py")}
    assert page and page <= opening
    assert sorted(opening - marked) == []


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
    and none named in `JSTACK_TEST_BROWSER`: how it ended, and what it printed. It is given the
    browser tests' folder, which holds every browser test (the test above), so that it does not
    collect the rest of the tree only to leave it out."""
    named = ("GITHUB_ACTIONS", "JSTACK_TEST_BROWSER")
    env = {name: value for name, value in outside_a_run().items() if name not in named}
    (tmp_path / "bin").mkdir(exist_ok=True)
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
        + ["--basetemp", str(tmp_path / "base"), *pytest_of("check-browser"), str(PAGE)],
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
