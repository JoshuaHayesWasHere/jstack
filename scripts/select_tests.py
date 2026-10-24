"""Which test files a change needs: `select_tests.py <base> <head>`.

It reads what changed with `git diff --name-only --no-renames <base> <head>`. It prints the
test files to run, sorted and one per line, or it prints `all`. It reads the imports of the
tree checked out here, so the same two commits give the same lines. It needs only the standard
library, so it runs before `uv sync`.

A changed module selects the test files that import it, directly or through any chain of modules. So
the script also selects a test file that imports a module that imports the changed module. The
module may be in `src/`, a feature's `features/<name>/src/`, the tests or `testing/`. The tests are
in `testing/tests/` and in each feature's own folder of tests, `features/<name>/tests/`. A test file
may sit in a folder below one of those, as `features/jbus/tests/view/test_view_bus.py` does. The
script counts such a file as importing the `conftest.py` of each folder it is in below that
`tests/`. A changed test file selects itself. The script counts a module that calls
`importlib.import_module` as importing every module under its directory.

A test may hold a string that is the name of a package of a `src/`. The script counts such a
test as running that package in a process of its own, so the test imports every module of the
package. A file in a package may be no module, such as a page or a pattern list. The script
reads a change to such a file as a change to the modules of a `src/` whose strings name it.
When no module names it, the change counts for the modules beside it.

A changed file that is no module (a doc, a skill, a hook) selects the test files that spell its
path, in the test file itself or in a test module it imports. A test spells a path with the parts of
a string or of a chain of `/` joins. The parts start at the file name and go up through the
directories until no other tracked file has the same ending: `crew` and `SKILL.md` spell
`features/crew/SKILL.md`. A file may include another: a line of a skill or a page that says to read
`$T/../skills/<its folder>/<name>.md` now includes that file beside it, and the tests read the
skill with it folded in. So a changed file that is included selects the tests that spell each file
that includes it, up the chain of includes. A changed fixture selects the tests that spell it or
the nearest directory above it. When no test spells either, the fixture selects `all`.

The map of verify-jstack's features, with each `features/<name>/verify.md`, adds more
selections. A feature file names the paths a feature owns (`Paths:`, in jmerge's pattern
syntax). It also names the tests that read those paths in a way no string shows (`Tests:`). A
changed path selects the `Tests:` of each feature that owns it. An edit to a feature file
selects that feature's tests: its `Tests:` and every test file that imports a module it owns.
The map's page, `CROSS`, lists the test files that read the whole tree (`Cross-cutting:`), and
every change runs them.

A test file that no change to any other path selects is owned by no rule: it imports nothing,
spells no path and is on no list. A change it reads in some other way (a glob, a walk) would merge
with it unrun. So every change also runs each such test, the catch-all, and the summary counts
it with the cross-cutting tests.

It prints `all` when the files it selected are `WHOLE` (80%) of the test files or more. Such a
run costs about what the whole suite does, and a whole run leaves the tree's marker. It also
prints `all` when a changed path is one that every test depends on. Those paths are
`pyproject.toml`, `uv.lock` and the root `conftest.py`. They also include each plugin of
`testing/` that the root `conftest.py` names in `pytest_plugins` (as
`testing/jstack_fixtures.py`), with the modules that plugin uses at its top level. And they
include each module that a plugin uses in an autouse fixture.

When `pytest_plugins` names a test module, pytest loads that module for its fixtures. A module
that only other fixtures use selects the tests that ask for those fixtures, directly or
through fixtures that use them. A plugin's own module counts as one its fixtures use. The
script does not print a test file the change deleted. It never prints a test module that marks
itself `browser`, because that module runs in the browser job.

With `$GITHUB_STEP_SUMMARY` set, it adds one line to that file: `check-fast selection=<all|some>
files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n>
forced-by=<path>`. The keys are always these, in this order. Each cause's count is the number of
files it selected on its own, so the counts overlap. `forced-by` names the path that made the
selection `all`. It is `share` when the selection's size made it `all`, and `-` otherwise. A
collector reads that line. With `$GITHUB_OUTPUT` set, it gives the step the output `selection`,
`all` or `some`: the check workflow leaves the tree's marker on a pass of `all`.

The diff is two-dot. So for a pull request, `<base>` is where it branched from main (`git
merge-base`) or the parent of its merge commit. A base that main has moved past adds main's own
changes to the diff, which selects more tests and never fewer.
"""

import ast
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
MAP = "testing/verify"
CROSS = "features/verify-jstack/project-skill/map.md"
PAGE = "verify.md"
TESTS = re.compile(r"((features/[^/]+|testing)/)?tests/")
SOURCE = re.compile(r"(features/[^/]+/)?src/")
TEST = re.compile(TESTS.pattern + r"(\w+/)*test_\w+\.py")
FIXTURES = re.compile(TESTS.pattern + "fixtures/")
SHARED = "testing/"
SHARED_TESTS = "testing/tests"
EVERYTHING = ("pyproject.toml", "uv.lock", "conftest.py")
BACKTICKED = re.compile(r"`([^`]+)`")
LABEL = re.compile(r"[A-Z][\w-]*:")
BROWSER = re.compile(r"^pytestmark\s*=.*\bpytest\.mark\.browser\b", re.M)
WORDS = re.compile(r"[\s/\\'\"`:=,()\[\]{}*|<>;]+")
INCLUDE = re.compile(r"read `\$T/\.\./skills/([^/`]+)/([^/`]+\.md)` now")


class Unread(Exception):
    """The script could not read a file the selection depends on, so it cannot tell that any
    path is outside the selection."""


@cache
def ready():
    """jmerge's reader of a list of paths, imported from this checkout's packages: `src/` and
    each feature's `src/`, as `install.sh` puts them on the path."""
    try:
        folders = [ROOT / "src", *sorted(ROOT.glob("features/*/src"))]
        sys.path[:0] = [str(folder) for folder in folders]
        from jmerge.ready import _protects, patterns_of
    except Exception as error:
        raise Unread(f"{type(error).__name__}: {error}") from error
    return SimpleNamespace(patterns_of=patterns_of, protects=_protects)


def listed(text, label):
    """The entries under the first line of `text` that starts with `label`: one backticked entry on
    each `- ` line after it, up to a blank line, the next `<Label>:` line or the end. This raises
    `Unread` if the label line holds an entry, or if a line in the list is not one backticked entry
    after `- `."""
    lines = text.splitlines()
    for at, line in enumerate(lines):
        if line.startswith(f"{label}:"):
            if BACKTICKED.search(line):
                raise Unread(f"{label}: holds an entry on the label line: {line}")
            entries = []
            for item in lines[at + 1 :]:
                if not item.strip() or LABEL.match(item):
                    break
                found = BACKTICKED.fullmatch(item[2:]) if item.startswith("- ") else None
                if not found:
                    raise Unread(f"{label}: has a line that is not one entry: {item}")
                entries.append(found[1])
            return entries
    return []


@cache
def pages():
    """Each feature file's name, with its path: `<MAP>/<name>.md`, or `features/<name>/verify.md`
    once the feature's page has moved into its folder."""
    found = {path.stem: path for path in sorted((ROOT / MAP).glob("*.md")) if path.stem != "README"}
    for path in sorted(ROOT.glob(f"features/*/{PAGE}")):
        name = path.parent.name
        if name in found:
            raise Unread(f"{path.relative_to(ROOT)}: the feature {name} also has {found[name]}")
        found[name] = path
    return {name: path.relative_to(ROOT).as_posix() for name, path in sorted(found.items())}


@cache
def features():
    """Each feature file's name, with its `Paths:` and its `Tests:`."""
    texts = {name: (ROOT / path).read_text() for name, path in pages().items()}
    return {name: (listed(text, "Paths"), listed(text, "Tests")) for name, text in texts.items()}


def cross_cutting():
    return listed((ROOT / CROSS).read_text(), "Cross-cutting")


def owns(patterns, path):
    return any(ready().protects(pattern, path) for pattern in patterns)


def of_tests(path):
    """Whether a path is the tests' own: under `testing/tests/`, a feature's `tests/`, or
    `testing/`."""
    return bool(TESTS.match(path)) or path.startswith(SHARED)


def plumbing(path):
    """Whether a path is of `testing/`, the package every test loads, and not of the repo's own
    tests under it."""
    return path.startswith(SHARED) and not TESTS.match(path)


@cache
def modules():
    """Every module of `src/`, of each feature's `src/`, of each folder of tests and of
    `testing/`, by its dotted name, with the path of its file from the root. pytest's `pythonpath`
    lists each folder of tests: `testing/tests/` and each feature's own `tests/`. So the modules in
    a folder of tests take their names from that folder. A module in a folder below it gets a name
    such as `view.scene`. Such a folder is a package, so pytest does not mistake its `conftest.py`
    for the `conftest.py` of a root. `testing/` is a package at the root, so its modules are
    `testing.<name>`. Its `tests/` is the exception: it is a folder of tests, so its modules take
    their names from that folder. The fixtures' folders hold no module."""
    roots = [
        ROOT / "src",
        *sorted(ROOT.glob("features/*/src")),
        ROOT / SHARED_TESTS,
        *sorted(ROOT.glob("features/*/tests")),
        ROOT,
    ]
    found = {}
    for root in roots:
        files = (root / SHARED).rglob("*.py") if root == ROOT else root.rglob("*.py")
        for path in sorted(files):
            named = path.relative_to(ROOT).as_posix()
            if root == ROOT and not plumbing(named):
                continue
            parts = list(path.relative_to(root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            if not FIXTURES.match(named):
                found[".".join(parts)] = named
    return found


def spelled(node):
    """The parts of a path a node spells: the strings of a chain of `/`, each part a string
    or `None` where it is not one."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return spelled(node.left) + spelled(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [part for part in node.value.split("/") if part]
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("Path", "PurePath"):
        return [part for arg in node.args for part in spelled(arg)]
    return [None]


def read(tree):
    """Return what this script reads from a module's tree: the names the module imports, the
    words of its string constants, whether it imports by name, the names of its functions'
    arguments, and the paths it spells."""
    names, words, dynamic, args, paths = set(), set(), False, set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Call):
            called = getattr(node.func, "attr", getattr(node.func, "id", ""))
            dynamic |= called in ("import_module", "__import__")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            words |= {node.value, *WORDS.split(node.value)}
            paths.add(tuple(spelled(node)))
        elif isinstance(node, ast.arg):
            args.add(node.arg)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            paths.add(tuple(spelled(node)))
    return names, words, dynamic, args, paths


def parents(name):
    parts = name.split(".")
    return {".".join(parts[:end]) for end in range(1, len(parts) + 1)}


@cache
def sources():
    """Each module, with what `read` finds in its source."""
    found = {}
    for name, path in modules().items():
        try:
            found[name] = read(ast.parse((ROOT / path).read_text()))
        except SyntaxError as error:
            raise Unread(f"{path}: {error}") from error
    return found


@cache
def edges():
    """Each module, with the modules it imports. A test may spell the name of a package in a `src/`
    folder. The script then counts the test as running that package in a process of its own, and so
    as importing every module of the package."""
    known = modules()
    packages = {}
    for path in known.values():
        if at := SOURCE.match(path):
            package = path[at.end() :].split("/")[0]
            packages[package] = path[: at.end()] + package
    found = {}
    for name, (names, _, dynamic, _, paths) in sources().items():
        reached = set().union(*map(parents, names)) & known.keys()
        if dynamic:
            below = Path(known[name]).parent.as_posix() + "/"
            reached |= {other for other, path in known.items() if path.startswith(below)}
        if of_tests(known[name]):
            run = tuple(
                f"{packages[one]}/"
                for one in packages.keys() & {one[0] for one in paths if len(one) == 1}
            )
            reached |= {other for other, path in known.items() if path.startswith(run)}
        if TEST.fullmatch(known[name]):
            reached |= conftests(name) & known.keys()
        found[name] = reached - {name}
    return found


def conftests(name):
    """The `conftest` of each folder of `tests/` a test module is in, below `tests/` itself:
    its fixtures reach the test with no import."""
    parts = name.split(".")[:-1]
    return {".".join(parts[:end] + ["conftest"]) for end in range(1, len(parts) + 1)}


@cache
def imported_by():
    """Each module, with the modules that import it directly."""
    found = {}
    for name, reached in edges().items():
        for one in reached:
            found.setdefault(one, set()).add(name)
    return found


def importers(names):
    """The modules that import any of `names`, through any chain, and `names` themselves."""
    found, todo = set(), list(names)
    while todo:
        one = todo.pop()
        if one not in found:
            found.add(one)
            todo += imported_by().get(one, ())
    return found


def test_files(names):
    return {modules()[name] for name in names if TEST.fullmatch(modules()[name])}


@cache
def spells(name):
    """The paths a test module spells, and the test modules it imports."""
    found, todo, seen = set(), [name], set()
    while todo:
        one = todo.pop()
        if one not in seen and of_tests(modules()[one]):
            seen.add(one)
            todo += edges()[one]
            found |= sources()[one][4]
    return frozenset(found)


def inside(parts, spelling):
    """Whether `parts` are in `spelling`, one after the other."""
    return any(spelling[at : at + len(parts)] == parts for at in range(len(spelling)))


@cache
def tracked():
    ran = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if ran.returncode:
        raise Unread(f"git ls-files failed: {ran.stderr.strip()}")
    return frozenset(ran.stdout.splitlines())


def called(path):
    """The parts of a path a test spells to name it: its file name, and with it the directories
    above it until no other file has the same ending."""
    parts = path.split("/")
    for start in range(len(parts) - 1, -1, -1):
        ending = "/".join(parts[start:])
        if not [one for one in tracked() - {path} if f"/{one}".endswith(f"/{ending}")]:
            return tuple(parts[start:])
    return tuple(parts)


@cache
def spelled_by():
    """The test files that spell each run of consecutive parts of a spelled path. It gives the
    result of `inside` for every test file at once, and reads each file once."""
    found = {}
    for name, path in modules().items():
        if TEST.fullmatch(path):
            for spelling in spells(name):
                for start in range(len(spelling)):
                    for end in range(start + 1, len(spelling) + 1):
                        found.setdefault(spelling[start:end], set()).add(path)
    return found


@cache
def included():
    """Each file another tracked file includes, with the files that include it. A file includes
    the file beside it that one of its lines says to read now, in the shape `INCLUDE` matches:
    the tests read a skill with each such file folded in."""
    found = {}
    for path in sorted(tracked()):
        if path.endswith(".md") and (ROOT / path).is_file():
            folder = Path(path).parent
            for line in (ROOT / path).read_text().splitlines():
                for skill, name in INCLUDE.findall(line):
                    if skill == folder.name and name != "SKILL.md":
                        found.setdefault((folder / name).as_posix(), set()).add(path)
    return found


def includers(path):
    """The files that include this path, and the files that include those, up the chain."""
    found, todo = set(), [path]
    while todo:
        for one in included().get(todo.pop(), ()):
            if one not in found:
                found.add(one)
                todo.append(one)
    return found


def readers(path):
    """The test files that spell this path, in a path of their own or of a module they import."""
    return set(spelled_by().get(called(path), ()))


def fixture_readers(path):
    """The test files that name a fixture, or that name the nearest directory above the
    fixture."""
    folder = FIXTURES.match(path)[0]
    parts = path.removeprefix(folder).split("/")
    for end in range(len(parts), 0, -1):
        found = readers(folder + "/".join(parts[:end]))
        if found:
            return found
    return set()


def feature_tests(name):
    """A feature's tests: its `Tests:` and the test files that import a module it owns."""
    owned, listed_tests = features()[name]
    mine = [one for one, path in modules().items() if owns(owned, path)]
    return set(listed_tests) | test_files(importers(mine))


def users(path):
    """The modules of a `src/` that use a file that is not a Python module. They are the modules
    whose strings name the file. When no module's strings name it, they are the modules in the
    file's directory."""
    parts = called(path)
    named = {
        name
        for name, one in sources().items()
        if SOURCE.match(modules()[name]) and any(inside(parts, spelling) for spelling in one[4])
    }
    here = Path(path).parent.as_posix() + "/"
    beside = {
        name
        for name, one in modules().items()
        if one.startswith(here) and "/" not in one.removeprefix(here)
    }
    return named or beside


def modules_named(tree):
    """The tests' own modules that a tree's imports name, by the name each is bound to."""
    bound = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bound |= {(a.asname or a.name).split(".")[0]: a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            bound |= {a.asname or a.name: node.module for a in node.names}
    return {local: name for local, name in bound.items() if of_tests(modules().get(name, ""))}


def plugins():
    """The modules the root `conftest.py` names in `pytest_plugins`, which every test loads."""
    for node in ast.parse((ROOT / "conftest.py").read_text()).body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "pytest_plugins":
            return [one.value for one in node.value.elts if modules().get(one.value)]
    return []


def used(node, bound):
    """The modules that a node uses, from `bound`, which maps each name to the module it is
    bound to."""
    return {
        bound[one.id] for one in ast.walk(node) if isinstance(one, ast.Name) and one.id in bound
    }


@cache
def conftest():
    """Which of the tests' modules the plugins of the root `conftest.py` load, as `(global,
    fixtures)`. The first is the set of modules every test loads. It holds each plugin of `testing/`
    (such as `testing.jstack_fixtures`) with the modules its top level uses. It also holds each
    other plugin that has an autouse fixture, with the modules that fixture uses. Any other plugin
    is a test module that the tests of other features import. pytest loads it for its fixtures, and
    a test that does not import it gets only those fixtures from it. The second maps each other
    fixture to the modules it uses and to the fixtures it asks for. If the fixture's plugin is a
    test module, the fixture's modules include that test module. So a change to a module selects
    every test that asks for a fixture that uses the module."""
    everyone, fixtures = set(), {}
    for plugin in plugins():
        tree = ast.parse((ROOT / modules()[plugin]).read_text())
        bound = modules_named(tree)
        whole = plumbing(modules()[plugin])
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            decorators = "".join(ast.unparse(one) for one in getattr(node, "decorator_list", ()))
            if "fixture" in decorators and "autouse=True" not in decorators:
                asks = {arg.arg for arg in node.args.args}
                fixtures[node.name] = (used(node, bound) | (set() if whole else {plugin}), asks)
            elif whole or "autouse=True" in decorators:
                everyone |= used(node, bound) | (set() if whole else {plugin})
    return everyone, fixtures


@cache
def shared():
    """The files every test loads: `EVERYTHING`, the plugins of `testing/`, and the modules
    the plugins use at their top level or in an autouse fixture, and those they import."""
    found, todo = set(), list(conftest()[0])
    while todo:
        one = todo.pop()
        if one not in found and of_tests(modules()[one]):
            found.add(one)
            todo += edges()[one]
    whole = {modules()[one] for one in plugins() if plumbing(modules()[one])}
    return {modules()[one] for one in found} | whole | set(EVERYTHING)


@cache
def defined(name):
    """The fixtures a module defines at its top level: a test that asks for one of them by name
    gets its own, and not a plugin's."""
    tree = ast.parse((ROOT / modules()[name]).read_text())
    return {
        node.name
        for node in tree.body
        if "fixture" in "".join(ast.unparse(one) for one in getattr(node, "decorator_list", ()))
    }


def own(name):
    """The fixtures a test file has of its own: its module's and its folders' `conftest`'s."""
    known = modules().keys()
    return set().union(*map(defined, {name} | (conftests(name) & known)))


def asking(module):
    """The test files that ask for a plugin's fixture that reaches `module`. The fixture
    reaches it when it uses `module`, uses a module that imports `module`, or asks for another
    fixture that reaches it. This leaves out a test file with its own fixture of that name."""
    reaching = importers([module])
    fixtures = conftest()[1]
    hit = {name for name, (used, _) in fixtures.items() if used & reaching}
    while more := {name for name, (_, asks) in fixtures.items() if asks & hit} - hit:
        hit |= more
    return {
        modules()[name]
        for name, (_, words, _, args, _) in sources().items()
        if TEST.fullmatch(modules()[name]) and (hit - own(name)) & (args | words)
    }


@cache
def opens_browser(test):
    """Whether the test file marks its whole module `browser`, which `make check-browser` runs
    and the check leaves out."""
    return bool(BROWSER.search((ROOT / test).read_text()))


def ruled(changed):
    """`(tests, why)`: the sorted test files the rules select for the changed paths, or
    `["all"]`, and for each cause the number of files it selected, or the path that forced
    `all`."""
    ready()
    for path in changed:
        if path in shared():
            return ["all"], {"forced-by": path}
    by_path = {path: name for name, path in modules().items()}
    found = {"imports": set(), "names": set(), "features": set()}
    for path in changed:
        if path in by_path:
            found["imports"] |= test_files(importers([by_path[path]])) | asking(by_path[path])
            if of_tests(path):
                found["names"] |= readers(path)
        elif FIXTURES.match(path):
            if not (named := fixture_readers(path)):
                return ["all"], {"forced-by": path}
            found["names"] |= named
        else:
            if SOURCE.match(path):
                found["imports"] |= test_files(importers(users(path)))
            for one in {path} | includers(path):
                found["names"] |= readers(one)
    where = pages()
    for name, (owned, listed_tests) in features().items():
        if any(owns(owned, path) for path in changed):
            found["features"] |= set(listed_tests)
        if where[name] in changed:
            found["features"] |= feature_tests(name)
    found["cross-cutting"] = set(cross_cutting())
    present = {
        key: {one for one in tests if (ROOT / one).is_file() and not opens_browser(one)}
        for key, tests in found.items()
    }
    return sorted(set().union(*present.values())), {key: len(one) for key, one in present.items()}


def collected():
    """The test files the check runs: each one there is, but the ones marked `browser`."""
    return {
        one
        for one in modules().values()
        if TEST.fullmatch(one) and (ROOT / one).is_file() and not opens_browser(one)
    }


@cache
def unowned():
    """The test files no rule owns: a change to every tracked path but the test itself selects
    none of them, where it does not select `all`."""
    owned = set()
    for path in sorted(tracked()):
        tests, _ = ruled([path])
        if tests != ["all"]:
            owned |= set(tests) - {path}
    return frozenset(collected() - owned)


def selection(changed):
    """`(tests, why)`: the sorted test files the changed paths need, or `["all"]`, and for
    each cause the number of files it selected, or the path that forced `all`. They are what
    the rules select and the test files no rule owns, counted as cross-cutting."""
    tests, why = ruled(changed)
    if tests == ["all"]:
        return tests, why
    lone = unowned()
    why = {**why, "cross-cutting": len(set(cross_cutting()) & collected() | lone)}
    return sorted(set(tests) | lone), why


CAUSES = ("imports", "names", "features", "cross-cutting")
WHOLE = 0.8


def total():
    return len([one for one in modules().values() if TEST.fullmatch(one)])


def whole(tests, why):
    """The selection as the check runs it: `all` when it holds `WHOLE` of the test files or
    more. Such a selection costs about what the whole suite does, and running the whole suite
    leaves the tree's marker."""
    if tests != ["all"] and len(tests) >= WHOLE * total():
        return ["all"], {**why, "forced-by": "share"}
    return tests, why


def summary(tests, why, changed):
    chosen = "all" if tests == ["all"] else "some"
    count = total() if chosen == "all" else len(tests)
    causes = " ".join(f"{key}={why.get(key, 0)}" for key in CAUSES)
    return (
        f"check-fast selection={chosen} files={count} of={total()} changed={len(changed)} "
        f"{causes} forced-by={why.get('forced-by', '-')}"
    )


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
    changed = diff.stdout.splitlines()
    try:
        tests, why = selection(changed)
    except Unread as error:
        print(f"select_tests.py: nothing can be read ({error}), so all", file=sys.stderr)
        tests, why = ["all"], {"forced-by": "unread"}
    tests, why = whole(tests, why)
    print("\n".join(tests))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as file:
            file.write(summary(tests, why, changed) + "\n\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as file:
            file.write(f"selection={'all' if tests == ['all'] else 'some'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
