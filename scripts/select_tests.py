"""Which test files a change needs: `select_tests.py <base> <head>`.

It reads what changed with `git diff --name-only --no-renames <base> <head>` and prints, one per
line and sorted, the test files to run, or `all`. It reads the imports of the tree checked out
here, so the same two commits give the same lines. It needs only the standard library, so it
runs before `uv sync`.

A changed module, of `src/` or a feature's `features/<name>/src/`, of the tests or of `testing/`,
selects the test files that import it, directly or through any chain of modules: a test file
that imports a module that imports it is selected too. The tests are in `tests/` and in each
feature's own, `features/<name>/tests/`.
A test file may be in a folder of one, as `features/jbus/tests/view/test_view_bus.py`, and is taken to import
the `conftest.py` of each folder it is in below that `tests/`. A changed test file is
selected itself. A module that calls `importlib.import_module` is taken to import every module
under its directory. A test with a string that is the name of a package of a `src/` is taken to
run it in a process of its own, and to import every module of it. A file in a package that is
no module (a page, a pattern list) is read as a change to the modules of a `src/` whose strings
name it, and with none to the modules beside it.

A changed file that is no module (a doc, a skill, a hook) selects the test files that spell its
path, in the file or in a test module it imports: the parts of a path in a string or a `/`
chain, from its file name up the directories until no other tracked file ends alike, as `crew`
and `SKILL.md` for `features/crew/SKILL.md`. A fixture selects the tests that spell it or the
nearest directory above it, and `all` where none does. The map of verify-jstack's features,
with each `features/<name>/verify.md`, adds to this: a feature file names the paths a feature
owns (`Paths:`, in jmerge's pattern syntax) and the tests that read them in a way no string
shows (`Tests:`), and a changed path
selects the `Tests:` of each feature that owns it. An edit to a feature file selects that
feature's tests: its `Tests:` and every test file that imports a module it owns. The map's
page, `CROSS`, lists the test files that read the whole tree (`Cross-cutting:`), which every change runs.

It prints `all` when the files it selected are `WHOLE` (80%) of the test files or more: such
a run costs about what the whole suite does, and run whole it leaves the tree's marker. And
it prints `all` when a changed path is one every test rests on: `pyproject.toml`, `uv.lock`,
the root `conftest.py`, a plugin it names in `pytest_plugins` from `testing/` (as
`testing/jstack_fixtures.py`) and the modules that one uses at its top level, or a module any
plugin uses in an autouse fixture. A test module named there is loaded for its fixtures. A
module only other fixtures use
selects the tests that ask for those fixtures, directly or through fixtures that use them, and
a plugin's own module is one its fixtures use. A test file the change deleted is not
printed. A test module that marks itself `browser` is never printed: it runs in the browser
job.

With `$GITHUB_STEP_SUMMARY` set it adds one line to that file: `check-fast selection=<all|some>
files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n>
forced-by=<path>`: the keys are always these, in this order, each cause's count is the files
it selected on its own (they overlap), and `forced-by` is `-` unless the path it names made
the selection `all`, or `share` where its size did. A collector reads that line. With
`$GITHUB_OUTPUT` set it gives the step the output `selection`, `all` or `some`: the check
workflow leaves the tree's marker on a pass of `all`.

The diff is two-dot, so for a pull request `<base>` is where it left main (`git merge-base`)
or the parent of its merge commit: a base main has moved past adds main's own changes, which
selects more and never less.
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
MAP = ".claude/skills/verify-jstack/features"
CROSS = "features/verify-jstack/project-skill/map.md"
PAGE = "verify.md"
TESTS = re.compile(r"(features/[^/]+/)?tests/")
SOURCE = re.compile(r"(features/[^/]+/)?src/")
TEST = re.compile(TESTS.pattern + r"(\w+/)*test_\w+\.py")
FIXTURES = re.compile(TESTS.pattern + "fixtures/")
SHARED = "testing/"
EVERYTHING = ("pyproject.toml", "uv.lock", "conftest.py")
BACKTICKED = re.compile(r"`([^`]+)`")
LABEL = re.compile(r"[A-Z][\w-]*:")
BROWSER = re.compile(r"^pytestmark\s*=.*\bpytest\.mark\.browser\b", re.M)
WORDS = re.compile(r"[\s/\\'\"`:=,()\[\]{}*|<>;]+")


class Unread(Exception):
    """A file the selection rests on could not be read, so no path is known to be outside."""


@cache
def ready():
    """jmerge's reading of a list of paths, from this checkout's packages: `src/` and each
    feature's `src/`, as `install.sh` puts them on the path."""
    try:
        folders = [ROOT / "src", *sorted(ROOT.glob("features/*/src"))]
        sys.path[:0] = [str(folder) for folder in folders]
        from jmerge.ready import _protects, patterns_of
    except Exception as error:
        raise Unread(f"{type(error).__name__}: {error}") from error
    return SimpleNamespace(patterns_of=patterns_of, protects=_protects)


def listed(text, label):
    """The entries under the first line of `text` that starts with `label`: one backticked entry
    on each `- ` line after it, up to a blank line, the next `<Label>:` line or the end. A label
    line that holds an entry, or any other line before the list ends, is a map no line per entry
    keeps apart."""
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


def features():
    """Each feature file's name, with its `Paths:` and its `Tests:`."""
    texts = {name: (ROOT / path).read_text() for name, path in pages().items()}
    return {name: (listed(text, "Paths"), listed(text, "Tests")) for name, text in texts.items()}


def cross_cutting():
    return listed((ROOT / CROSS).read_text(), "Cross-cutting")


def owns(patterns, path):
    return any(ready().protects(pattern, path) for pattern in patterns)


def of_tests(path):
    """Whether a path is the tests' own: under `tests/`, a feature's `tests/`, or `testing/`."""
    return bool(TESTS.match(path)) or path.startswith(SHARED)


@cache
def modules():
    """Every module of `src/` and of each feature's `src/`, of each folder of tests and of
    `testing/`, by its dotted name:
    the file it is, from the root. Each folder of tests, `tests/` and each feature's own, is on
    pytest's path, so its modules are named from it: a module in a folder below it as
    `view.scene`, such a folder being a package, so its `conftest.py` is not taken for a root's.
    `testing/` is a package at the root, so its modules are `testing.<name>`. The fixtures'
    folders hold none."""
    roots = [
        ROOT / "src",
        *sorted(ROOT.glob("features/*/src")),
        ROOT / "tests",
        *sorted(ROOT.glob("features/*/tests")),
        ROOT,
    ]
    found = {}
    for root in roots:
        files = (root / SHARED).rglob("*.py") if root == ROOT else root.rglob("*.py")
        for path in sorted(files):
            named = path.relative_to(ROOT).as_posix()
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
    """What a module's source says: the names it imports, the words of its string constants,
    whether it imports by name, the names of its functions' arguments, and the paths it spells."""
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
    """Each module, read."""
    found = {}
    for name, path in modules().items():
        try:
            found[name] = read(ast.parse((ROOT / path).read_text()))
        except SyntaxError as error:
            raise Unread(f"{path}: {error}") from error
    return found


@cache
def edges():
    """Each module, with the modules it imports. A test that spells the name of a package of
    a `src/` is taken to run it in a process of its own, so it imports every module of it."""
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


def importers(names):
    """The modules that import any of `names`, through any chain, and `names` themselves."""
    by_imported = {}
    for name, reached in edges().items():
        for one in reached:
            by_imported.setdefault(one, set()).add(name)
    found, todo = set(), list(names)
    while todo:
        one = todo.pop()
        if one not in found:
            found.add(one)
            todo += by_imported.get(one, ())
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
    """Each run of parts, one after the other, in a path a test file spells, with the test
    files that spell it: `inside` for every test file at once, read once."""
    found = {}
    for name, path in modules().items():
        if TEST.fullmatch(path):
            for spelling in spells(name):
                for start in range(len(spelling)):
                    for end in range(start + 1, len(spelling) + 1):
                        found.setdefault(spelling[start:end], set()).add(path)
    return found


def readers(path):
    """The test files that spell this path, in a path of their own or of a module they import."""
    return set(spelled_by().get(called(path), ()))


def fixture_readers(path):
    """The test files that name a fixture, or the nearest directory above it that one names."""
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
    """The modules of a `src/` that use a file that is no module: the ones whose strings name
    it, or with none the modules in its directory."""
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
    """The modules of `bound`, a name to the module it is bound to, that a node uses."""
    return {
        bound[one.id] for one in ast.walk(node) if isinstance(one, ast.Name) and one.id in bound
    }


@cache
def conftest():
    """What the plugins of the root `conftest.py` make of the tests' modules: `(global,
    fixtures)`. The first is the modules every test loads: each plugin of `testing/`, as
    `testing.jstack_fixtures`, with the modules its top level uses, and each other plugin with
    an autouse fixture, with the modules that fixture uses. Any other plugin, a test module the
    tests of other features import, is loaded for its fixtures, and those alone reach a test
    that does not import it. The second is each other fixture, with the modules it uses, a test
    module's plugin among them, and the fixtures it asks for, so a change to a module reaches
    the tests that ask for a fixture that uses it."""
    everyone, fixtures = set(), {}
    for plugin in plugins():
        tree = ast.parse((ROOT / modules()[plugin]).read_text())
        bound = modules_named(tree)
        whole = modules()[plugin].startswith(SHARED)
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
    whole = {modules()[one] for one in plugins() if modules()[one].startswith(SHARED)}
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
    """The test files that ask for a fixture of a plugin that uses `module`, or uses a module
    that imports it, or asks for one that does, and have no fixture of that name of their own."""
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


def selection(changed):
    """`(tests, why)`: the sorted test files the changed paths need, or `["all"]`, and for
    each cause the number of files it selected, or the path that forced `all`."""
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
            found["names"] |= readers(path)
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


CAUSES = ("imports", "names", "features", "cross-cutting")
WHOLE = 0.8


def total():
    return len([one for one in modules().values() if TEST.fullmatch(one)])


def whole(tests, why):
    """The selection as it is run: `all` where it is `WHOLE` of the test files or more, which
    costs about what the whole suite does and, run whole, leaves the tree's marker."""
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
