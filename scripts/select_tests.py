"""Which test files a change needs: `select_tests.py <base> <head>`.

It reads what changed with `git diff --name-only --no-renames <base> <head>`, and the map of
verify-jstack's features, whose files each say which paths a feature owns (`Paths:`) and which
test files are its tests (`Tests:`). Its README lists the test files that read the whole tree
(`Cross-cutting:`), which every change runs.

It prints `all` when a changed path is one the whole suite rests on: a path of
`src/jmerge/ci-paths.txt`, `tests/conftest.py` or any other file under `tests/` that is not a
test module (`tests/fixtures/`), the map, this script, or the code it reads a pattern with.
Otherwise it prints, one per line and sorted, the cross-cutting test files, the test files
that changed and every test module that imports one of them, and the tests of each feature
that owns a changed path. A test module that `tests/conftest.py` imports is one every test
loads, so a change to it is `all` too. A test file the change deleted is not printed.

The map and the tests are read from the tree checked out here, so the same two commits give
the same lines. A pattern is read as jmerge reads `ci-paths.txt`, by jmerge's own code, which
needs no package: like `green_tree.py`, this runs before `uv sync`. Where that code cannot be
loaded, it prints `all`.
"""

import re
import subprocess
import sys
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ".cursor/skills/verify-jstack/features"
CI_PATHS = "src/jmerge/ci-paths.txt"
ITSELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
MATCHER = ("/src/jmerge/__init__.py", "/src/jmerge/ready.py", "/src/jmerge/rangediff.py")
EVERYTHING = (f"/{ITSELF}", f"/{MAP}/", "/tests/conftest.py", "/src/jsettings/", *MATCHER)
TEST = re.compile(r"tests/test_\w+\.py")
BACKTICKED = re.compile(r"`([^`]+)`")
IMPORTED = re.compile(r"^\s*(?:from|import) (\w+)", re.M)


class Unread(Exception):
    """jmerge's reading of a pattern could not be loaded, so no path is known to be outside."""


@cache
def ready():
    """jmerge's reading of a list of paths, from this checkout's `src/`."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from jmerge import ready
    except Exception as error:
        raise Unread(f"{type(error).__name__}: {error}") from error
    return ready


def listed(text, label):
    """The backticked entries of the first line of `text` that starts with `label`."""
    for line in text.splitlines():
        if line.startswith(f"{label}:"):
            return BACKTICKED.findall(line)
    return []


def features():
    """Each feature file's name, with its `Paths:` and its `Tests:`."""
    texts = {path.stem: path.read_text() for path in sorted((ROOT / MAP).glob("*.md"))}
    return {
        name: (listed(text, "Paths"), listed(text, "Tests"))
        for name, text in texts.items()
        if name != "README"
    }


def cross_cutting():
    return listed((ROOT / MAP / "README.md").read_text(), "Cross-cutting")


def everything():
    """The patterns whose change runs the whole suite."""
    return (*ready().patterns_of((ROOT / CI_PATHS).read_text()), *EVERYTHING)


def owns(patterns, path):
    return any(ready()._protects(pattern, path) for pattern in patterns)


def whole(path):
    """Whether a change to this path runs the whole suite: one of `everything`, or a file
    under `tests/` that is no test module, which any test may read."""
    if path.startswith("tests/") and not TEST.fullmatch(path):
        return True
    return owns(everything(), path)


def importers(changed):
    """The changed test modules, and every module under `tests/` that imports one of them."""
    modules = {path.stem: path for path in (ROOT / "tests").glob("*.py")}
    imports = {name: set(IMPORTED.findall(path.read_text())) for name, path in modules.items()}
    found = {Path(path).stem for path in changed if TEST.fullmatch(path)}
    while more := {name for name, names in imports.items() if names & found} - found:
        found |= more
    return {f"tests/{name}.py" for name in found}


def selected(changed):
    """`all`, or the sorted test files the changed paths need."""
    if any(whole(path) for path in changed):
        return ["all"]
    tests = importers(changed)
    if "tests/conftest.py" in tests:
        return ["all"]
    for owned, listed_tests in features().values():
        if any(owns(owned, path) for path in changed):
            tests |= set(listed_tests)
    tests |= set(cross_cutting())
    return sorted(test for test in tests if (ROOT / test).is_file())


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: select_tests.py <base> <head>")
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode:
        sys.exit(f"select_tests.py: git diff failed: {diff.stderr.strip()}")
    try:
        lines = selected(diff.stdout.splitlines())
    except Unread as error:
        print(f"select_tests.py: no pattern can be read ({error}), so all", file=sys.stderr)
        lines = ["all"]
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:])
