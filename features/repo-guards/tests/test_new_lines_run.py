"""Each line a branch adds to a feature's code runs in a test that names that code.

The class has been upheld four times, as "a new branch with no test": #952's swallow of a failed
migration, #963's unread compare of `_on_red`, #969's remark that did not go, and #941's merge
commit git lacks. Each was a review finding. The test makes the first three a red check instead.
#941's is out of its reach: the fix added a condition to a line whose `if` the tests took both
ways, and a line that runs is all this test sees.

The lines are those the worktree adds to a Python file of a feature's `src/` or `scripts/` since
the merge-base with the base ref (`BASE`, else `origin/main`, as `test_run_not_read.base` finds
it), a new file's every line among them. The tests are each test file that names the file's
module: one that imports it, or spells its dotted name, as `jbus.stall` or `jbus.stall.twice`, or,
for a script, spells its file name, as `force_pushes.py`. The test runs those under coverage,
with the processes they start, and fails on each added line that is a statement none of them ran.
The run stops once each file's lines have run, or once every test that names the file has ended
(`features/repo-guards/ran/lines_ran.py`), so a branch whose lines a few tests run pays for those
and not for every test that names its module, and a line no test runs is listed once the tests
that name its module have ended, not the tests that name every other module the branch touches.

An exception is coverage's own pragma on the line, with its reason and the user's word:
`# pragma: no cover, <reason> (the user, <when>: "<their words>")`. An added pragma without them
fails.
"""

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import coverage
import pytest

from test_run_not_read import base, git
from testing.paths import REPO

CODE = re.compile(r"features/[^/]+/(src|scripts)/.+\.py")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.M)
PRAGMA = re.compile(r"#\s*pragma[:\s]?\s*no\s*cover", re.I)
EXCEPTION = re.compile(r"#\s*pragma: no cover, \S.*?\(the user[,:]\s*[^)]*\S\)\s*$")
TESTS = ("features/*/tests/**/test_*.py", "testing/tests/**/test_*.py")
WORKERS = "4"
RAN = Path(__file__).parents[1] / "ran"
SPEC = importlib.util.spec_from_file_location("new_lines_rounds", RAN / "new_lines_rounds.py")
rounds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rounds)


def added(since: str, repo: Path = REPO) -> dict[str, set[int]]:
    """Each file of a feature's code the worktree adds lines to since `since`, with those lines."""
    found: dict[str, set[int]] = {}
    for path in git("diff", "--name-only", "--diff-filter=d", since, repo=repo).splitlines():
        if CODE.fullmatch(path):
            diff = git("diff", "-U0", since, "--", path, repo=repo)
            for start, count in HUNK.findall(diff):
                lines = range(int(start), int(start) + int(count or 1))
                found.setdefault(path, set()).update(lines)
    for path in git("ls-files", "--others", "--exclude-standard", repo=repo).splitlines():
        if CODE.fullmatch(path):
            found[path] = set(range(1, len((repo / path).read_text().splitlines()) + 1))
    return {path: lines for path, lines in found.items() if lines}


def named(path: str) -> tuple[str | None, re.Pattern[str]]:
    """The module of `path` by its dotted name (None for a script), and what a test spells to name
    it: that name, or a script's file name. A package's own top is named only by an import of it,
    since every test of its feature spells the package's name."""
    place = Path(path)
    if place.parts[2] == "scripts":
        return None, re.compile(rf"\b{re.escape(place.name)}\b")
    parts = list(place.with_suffix("").parts[3:])
    if parts[-1] == "__init__":
        parts.pop()
    dotted = ".".join(parts)
    return dotted, re.compile(rf"\b{re.escape(dotted)}\b" if len(parts) > 1 else r"(?!)")


def imported(source: str) -> set[str]:
    """Each module a test's source imports by name, with each name it imports from one."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    return found


def naming(paths: list[str], repo: Path = REPO) -> list[str]:
    """The test files that name any of `paths`."""
    tests = sorted({one for pattern in TESTS for one in repo.glob(pattern)} - {Path(__file__)})
    sources = {one: one.read_text() for one in tests if "fixtures" not in one.parts}
    found = set()
    for dotted, spelling in map(named, paths):
        found |= {
            test.relative_to(repo).as_posix()
            for test, source in sources.items()
            if dotted in imported(source) or spelling.search(source)
        }
    return sorted(found)


def unexcused(lines: dict[str, set[int]], repo: Path = REPO) -> list[str]:
    """Each added pragma that gives no reason and no word of the user's."""
    found = []
    for path, numbers in lines.items():
        text = (repo / path).read_text().splitlines()
        found += [
            f"{path}:{number} skips coverage with no reason and no word of the user's: write "
            f'# pragma: no cover, <reason> (the user, <when>: "<their words>")'
            for number in sorted(numbers)
            if number <= len(text)
            and PRAGMA.search(text[number - 1])
            and not EXCEPTION.search(text[number - 1])
        ]
    return found


def unrun(
    lines: dict[str, set[int]],
    tests: list[str],
    naming: dict[str, list[str]],
    scratch: Path,
    repo: Path = REPO,
) -> dict[str, set[int]]:
    """The lines of `lines` that `tests` do not run. The run stops early once each file's lines
    have run, or once the tests among `tests` that name it (`naming`), all of `tests` when none
    does, have ended. A run that breaks, not one whose tests fail, fails the test with what pytest
    printed."""
    scratch.mkdir(parents=True, exist_ok=True)
    config = scratch / "coveragerc"
    config.write_text(
        "[run]\npatch = subprocess\n"
        f"data_file = {scratch / 'data'}\n"
        f"include =\n{''.join(f'    {repo / path}\n' for path in lines)}"
    )
    waited = scratch / "waited.json"
    stopped = scratch / "stopped"
    waited.write_text(
        json.dumps(
            {
                "lines": {str(repo / path): sorted(numbers) for path, numbers in lines.items()},
                "reach": {
                    str(repo / path): [
                        str(repo / one) for one in [t for t in naming[path] if t in tests] or tests
                    ]
                    for path in lines
                },
                "data": str(scratch / "data"),
                "stopped": str(stopped),
            }
        )
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_") and key not in ("COVERAGE_PROCESS_START", "NEW_LINES_TEST")
    }
    env["NEW_LINES_RAN"] = str(waited)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(RAN), env.get("PYTHONPATH")]))
    coverage = [sys.executable, "-m", "coverage"]
    pytest_run = [
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "lines_ran",
        "-n",
        WORKERS,
        "--dist",
        "worksteal",
    ]
    ran = subprocess.run(
        [*coverage, "run", f"--rcfile={config}", *pytest_run, "-m", "not browser", *tests],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    if ran.returncode not in (0, 1) and not (ran.returncode == 2 and stopped.exists()):
        pytest.fail(
            f"the tests that name the code did not run (exit {ran.returncode}):\n{ran.stdout}"
        )
    report = scratch / "coverage.json"
    for step in (["combine", "-q"], ["json", "-q", "-o", str(report)]):
        subprocess.run([*coverage, *step, f"--rcfile={config}"], cwd=repo, env=env, check=True)
    measured = {
        (repo / name).resolve(): data
        for name, data in json.loads(report.read_text())["files"].items()
    }
    found = {}
    for path, numbers in lines.items():
        data = measured.get((repo / path).resolve())
        if left := numbers & set(data["missing_lines"]) if data else numbers:
            found[path] = left
    return found


def unread(
    lines: dict[str, set[int]], tests: dict[str, list[str]], parts: Path
) -> dict[str, set[int]]:
    """The lines of `lines` that CI's parts did not run in a test file that names their module,
    read from what `features/repo-guards/ran/part_lines.py` wrote to `parts` as they ran their
    tests. A line that ran while no test did, as a module was imported at collection, counts
    once a test file that names its module ran in a part, since that file would have run it."""
    ran = {name for one in parts.glob("tests.*") for name in one.read_text().split()}
    found = {path: set(numbers) for path, numbers in lines.items()}
    for one in parts.glob("data*"):
        data = coverage.CoverageData(basename=str(one))
        data.read()
        for name in data.measured_files():
            for path in [path for path in found if name.endswith(f"/{path}")]:
                namers = set(tests[path])
                counted = namers | ({""} if namers & ran else set())
                found[path] -= {
                    number
                    for number, contexts in data.contexts_by_lineno(name).items()
                    if counted & set(contexts)
                }
    return {path: numbers for path, numbers in found.items() if numbers}


def statements(file: Path) -> set[int]:
    """The line each statement of `file` starts on, a docstring's left out: the lines coverage can
    say ran or not, so a branch that changes only words runs no test here."""
    return {
        node.lineno
        for node in ast.walk(ast.parse(file.read_text()))
        if isinstance(node, ast.stmt)
        and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    }


def faults(
    lines: dict[str, set[int]], scratch: Path, repo: Path = REPO, parts: Path | None = None
) -> list[str]:
    """What is wrong with the lines a branch adds: an unexcused pragma, or a statement no test that
    names its module runs. With `parts`, the folder of what CI's parts ran (`unread`), a line they
    ran in a test that names its module runs no test here. The tests run for the lines still
    unrun, in two rounds, so a module many tests name costs little when its own tests run its
    lines: first each module's own test files, those whose name holds the module's file name
    (`test_jbus_remarks.py` for `remarks.py`), then, for the lines still unrun, every other test
    that names the module."""
    lines = {path: numbers & statements(repo / path) for path, numbers in lines.items()}
    lines = {path: numbers for path, numbers in lines.items() if numbers}
    tests = {path: naming([path], repo) for path in lines}
    said = [
        f"{path}: no test names its module, so no test runs its added lines"
        for path in sorted(lines)
        if not tests[path]
    ]
    left = {path: numbers for path, numbers in lines.items() if tests[path]}
    if parts is not None:
        left = unread(left, tests, parts)
    own = {path: [one for one in tests[path] if Path(path).stem in Path(one).stem] for path in left}
    first = sorted({one for path in left for one in own[path]})
    if first:
        mine = unrun(
            {path: left[path] for path in left if own[path]}, first, tests, scratch / "own", repo
        )
        left = {
            path: mine.get(path, set()) if own[path] else numbers for path, numbers in left.items()
        }
        left = {path: numbers for path, numbers in left.items() if numbers}
    rest = rounds.second(left, tests, own)
    if left and rest:
        left = unrun(left, rest, tests, scratch / "rest", repo)
    said += [
        f"{path}:{number} is a line this branch adds that no test runs: add a test that runs it, "
        f"among the tests that name its module ({len(tests[path])} of them ran)"
        for path, numbers in sorted(left.items())
        for number in sorted(numbers)
    ]
    return unexcused(lines, repo) + said


@pytest.mark.timeout(900)
def test_every_line_this_branch_adds_to_a_feature_runs_in_a_test(tmp_path, request):
    """In CI's check each part records what its tests run (`part_lines.py`), and the job `check`
    runs this test once the parts end, with `NEW_LINES_PARTS` the folder of what they recorded,
    so no part runs a test a second time for it."""
    if request.config.pluginmanager.hasplugin("part_lines"):
        pytest.skip("this part records the lines its tests run, which the job check reads")
    since = base()
    if since is None:
        pytest.skip("no merge-base with origin/main here, so the added lines are not known")
    parts = os.environ.get("NEW_LINES_PARTS")
    found = faults(added(since), tmp_path, parts=Path(parts) if parts else None)
    assert found == [], "\n".join(found)


def test_an_added_branch_no_test_runs_fails_and_one_a_test_runs_passes(tmp_path):
    repo = tmp_path / "repo"
    code = repo / "features/pkg/src/pkg"
    tests = repo / "features/pkg/tests"
    code.mkdir(parents=True)
    tests.mkdir(parents=True)
    (code / "__init__.py").write_text("")
    (code / "held.py").write_text("def held(row):\n    return row == 'held'\n")
    (tests / "test_held.py").write_text(
        "import sys\n"
        "sys.path.insert(0, 'features/pkg/src')\n"
        "from pkg import held\n\n\n"
        "def test_a_held_row():\n"
        "    assert held.held('held')\n"
    )
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "base"]):
        git("-c", "user.name=t", "-c", "user.email=t@t", *args, repo=repo)
    since = git("rev-parse", "HEAD", repo=repo)
    (code / "held.py").write_text(
        "def held(row):\n"
        "    if row is None:\n"
        "        return False\n"
        "    if row == 'gone':\n"
        "        return False  # pragma: no cover\n"
        "    return row == 'held'\n"
    )
    lines = added(since, repo)
    assert lines == {"features/pkg/src/pkg/held.py": {2, 3, 4, 5}}
    assert faults(lines, tmp_path / "unrun", repo) == [
        "features/pkg/src/pkg/held.py:5 skips coverage with no reason and no word of the user's: "
        'write # pragma: no cover, <reason> (the user, <when>: "<their words>")',
        "features/pkg/src/pkg/held.py:3 is a line this branch adds that no test runs: add a test "
        "that runs it, among the tests that name its module (1 of them ran)",
    ]
    assert (tmp_path / "unrun/own/stopped").exists(), "the run went on after its tests had ended"
    (tests / "test_held.py").write_text(
        (tests / "test_held.py").read_text()
        + "\n\ndef test_no_row():\n    assert not held.held(None)\n"
    )
    (code / "held.py").write_text(
        (code / "held.py")
        .read_text()
        .replace(
            "# pragma: no cover",
            '# pragma: no cover, a row is never gone here (the user, 11-04: "fine")',
        )
    )
    assert faults(added(since, repo), tmp_path / "ran", repo) == []
    assert (tmp_path / "ran/own/stopped").exists(), "the run went on after every line had run"


def test_a_line_only_another_modules_own_test_runs_counts_as_run(tmp_path):
    repo = tmp_path / "repo"
    code = repo / "features/pkg/src/pkg"
    tests = repo / "features/pkg/tests"
    code.mkdir(parents=True)
    tests.mkdir(parents=True)
    (code / "__init__.py").write_text("")
    (code / "proved.py").write_text("def proved(row):\n    return row == 'proved'\n")
    (code / "ready.py").write_text("def ready(row):\n    return row == 'ready'\n")
    (tests / "test_proved.py").write_text(
        "import sys\n"
        "sys.path.insert(0, 'features/pkg/src')\n"
        "from pkg import proved, ready\n\n\n"
        "def test_a_proved_row_is_ready():\n"
        "    assert not proved.proved(None)\n"
        "    assert not ready.ready(None)\n"
    )
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "base"]):
        git("-c", "user.name=t", "-c", "user.email=t@t", *args, repo=repo)
    since = git("rev-parse", "HEAD", repo=repo)
    (code / "proved.py").write_text(
        "def proved(row):\n    if row is None:\n        return False\n    return row == 'proved'\n"
    )
    (code / "ready.py").write_text(
        "def ready(row):\n    if row is None:\n        return False\n    return row == 'ready'\n"
    )
    lines = added(since, repo)
    assert lines == {
        "features/pkg/src/pkg/proved.py": {2, 3},
        "features/pkg/src/pkg/ready.py": {2, 3},
    }
    assert faults(lines, tmp_path / "unrun", repo) == []


def test_an_untested_line_is_listed_once_its_own_tests_end_not_another_modules(tmp_path):
    repo = tmp_path / "repo"
    code = repo / "features/pkg/src/pkg"
    tests = repo / "features/pkg/tests"
    ended = tmp_path / "ended"
    code.mkdir(parents=True)
    tests.mkdir(parents=True)
    ended.mkdir()
    (code / "__init__.py").write_text("")
    (code / "held.py").write_text("def held(row):\n    return row == 'held'\n")
    (code / "slow.py").write_text("def slow(row):\n    return row\n")
    (tests / "test_held.py").write_text(
        "import sys\n"
        "import time\n"
        "sys.path.insert(0, 'features/pkg/src')\n"
        "from pkg import held\n\n\n"
        "def test_a_held_row():\n"
        "    assert held.held('held')\n\n\n"
        "def test_a_late_row():\n"
        "    time.sleep(1.5)\n"
        "    assert held.held('late')\n"
    )
    (tests / "test_slow.py").write_text(
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n\n"
        "import pytest\n\n"
        "sys.path.insert(0, 'features/pkg/src')\n"
        "from pkg import slow\n\n\n"
        "def test_no_row():\n"
        "    assert slow.slow(None) == 0\n\n\n"
        "@pytest.mark.parametrize('n', range(12))\n"
        "def test_a_slow_row(n):\n"
        "    time.sleep(2)\n"
        f"    Path({str(ended)!r}, str(n)).touch()\n"
    )
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "base"]):
        git("-c", "user.name=t", "-c", "user.email=t@t", *args, repo=repo)
    since = git("rev-parse", "HEAD", repo=repo)
    (code / "held.py").write_text(
        "def held(row):\n"
        "    if row is None:\n"
        "        return False\n"
        "    if row == 'late':\n"
        "        return True\n"
        "    return row == 'held'\n"
    )
    (code / "slow.py").write_text(
        "def slow(row):\n    if row is None:\n        return 0\n    return row\n"
    )
    assert faults(added(since, repo), tmp_path / "unrun", repo) == [
        "features/pkg/src/pkg/held.py:3 is a line this branch adds that no test runs: add a test "
        "that runs it, among the tests that name its module (1 of them ran)",
    ]
    assert (tmp_path / "unrun/own/stopped").exists(), "the run went on to its end"
    assert len(list(ended.iterdir())) < 12, "the run waited on every slow test of another module"


def a_part(repo: Path, since: str, folder: Path) -> None:
    """Run `repo`'s tests as one of CI's parts runs its own, with `part_lines`, on one worker, so
    the test files run in the order of their names."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_") and key not in ("COVERAGE_PROCESS_START", "NEW_LINES_TEST")
    }
    env |= {"NEW_LINES_PART": str(folder), "NEW_LINES_BASE": since}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(RAN), env.get("PYTHONPATH")]))
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "part_lines"]
        + ["-n", "1", "features/pkg/tests"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_the_check_reads_what_the_parts_ran_and_runs_no_test_again_for_a_line_they_ran(tmp_path):
    """A line a part ran in a test file that names its module, in the test's own process or one it
    started, passes on what the part recorded, with no test run again, also when a test file that
    ran before it in the same process ran it first. A line that ran only in a test that does not
    name its module, or not at all, is still a fault."""
    repo = tmp_path / "repo"
    code = repo / "features/pkg/src/pkg"
    tests = repo / "features/pkg/tests"
    runs = tmp_path / "runs"
    code.mkdir(parents=True)
    tests.mkdir(parents=True)
    runs.mkdir()
    (code / "__init__.py").write_text("")
    (code / "held.py").write_text("def held(row):\n    return row == 'held'\n")
    (tests / "test_held.py").write_text(
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "sys.path.insert(0, 'features/pkg/src')\n"
        "from pkg import held\n\n\n"
        "def test_a_held_row():\n"
        f"    open(os.path.join({str(runs)!r}, str(os.getpid())), 'a').write('ran\\n')\n"
        "    assert held.held('held')\n"
        "    assert held.late(1)\n"
    )
    (tests / "test_a_row.py").write_text(
        "import importlib\n"
        "import sys\n"
        "sys.path.insert(0, 'features/pkg/src')\n\n\n"
        "def test_a_row_of_no_module_this_names():\n"
        "    assert not importlib.import_module('pkg.' + 'held').held(None)\n"
        "    assert importlib.import_module('pkg.' + 'held').late(1)\n"
    )
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "base"]):
        git("-c", "user.name=t", "-c", "user.email=t@t", *args, repo=repo)
    since = git("rev-parse", "HEAD", repo=repo)
    (code / "held.py").write_text(
        "def held(row):\n    if row is None:\n        return False\n    return row == 'held'\n"
        "\n\ndef late(row):\n    return row\n"
    )
    a_part(repo, since, tmp_path / "unrun-parts")
    assert faults(added(since, repo), tmp_path / "unrun", repo, tmp_path / "unrun-parts") == [
        "features/pkg/src/pkg/held.py:3 is a line this branch adds that no test runs: add a test "
        "that runs it, among the tests that name its module (1 of them ran)",
    ]
    (tests / "test_held.py").write_text(
        (tests / "test_held.py").read_text() + "\n\ndef test_no_row():\n"
        "    code = 'import sys; sys.path.insert(0, \"features/pkg/src\"); from pkg import held'\n"
        "    subprocess.run([sys.executable, '-c', code + '; assert held.held(None) is False'],"
        " check=True)\n"
    )
    a_part(repo, since, tmp_path / "ran-parts")
    before = sum(len(one.read_text().split()) for one in runs.iterdir())
    assert faults(added(since, repo), tmp_path / "ran", repo, tmp_path / "ran-parts") == []
    assert sum(len(one.read_text().split()) for one in runs.iterdir()) == before, (
        "the check ran a test again for a line a part ran"
    )
