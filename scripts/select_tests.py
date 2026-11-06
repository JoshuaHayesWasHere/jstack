"""Which test files a change needs: `select_tests.py <base> <head>`.

It reads what changed with `git diff --name-only --no-renames <base> <head>`. It prints the
test files to run, sorted and one per line, or it prints `all`. It reads the imports of the
tree checked out here, so the same two commits give the same lines. It needs only the standard
library, so it runs before `uv sync`. It keeps what it read of each module in
`select_tests.facts` in the repo's git directory, by a hash of the module's text and of this
script, and parses again only a module whose text changed: the selection is the same with the
file or without it.

A changed module selects the test files that import it, directly or through any chain of modules. So
the script also selects a test file that imports a module that imports the changed module. The
module may be in `src/`, a feature's `features/<name>/src/`, the tests, `testing/`, a package of
`scripts/` or a folder a test puts on `sys.path` (`PATHS`). The tests are
in `testing/tests/` and in each feature's own folder of tests, `features/<name>/tests/`. A test file
may sit in a folder below one of those, as `features/jbus/tests/view/test_view_bus.py` does. The
script counts such a file as importing the `conftest.py` of each folder it is in below that
`tests/`. A changed test file selects itself. An import inside `if TYPE_CHECKING:` never runs,
so it counts for nothing. A call to `importlib.import_module` imports every module under the
directory of the module that holds it, but only when that code runs. So it counts for the module
itself when the module calls it on import, or when the module is one of the tests. Otherwise it
counts for each module that names the function that holds it, through its imports, a package
that re-exports it, or a star import. A call with a string also imports the module the string
names.

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
that includes it, up the chain of includes. A test may also name a skill and read it through
`testing.paths.skills()`, as `block("home", …)` of `test_home_thread` does. Where code the test
runs reads skills so, each skill that code names spells that skill's `SKILL.md`, and with it each
file the skill includes. That code is the test's own, a helper it calls or a fixture it asks for,
and what each runs in turn, through the module's names and its imports: a skill a module names
in a helper the test does not reach spells nothing for it. A changed fixture selects the
tests that spell it or the nearest directory above it. When no test spells either, the fixture
selects `all`.

The map of verify-jstack's features, with each `features/<name>/verify.md`, adds more
selections. A feature file names the paths a feature owns (`Paths:`, in jmerge's pattern
syntax). It also names the tests that read those paths in a way no string shows (`Tests:`). A
changed path selects the `Tests:` of each feature that owns it. An edit to a feature file
selects that feature's tests: its `Tests:` and every test file that imports a module it owns.
The map's page, `CROSS`, lists the test files that read the whole tree (`Cross-cutting:`), and
every change runs them.

A test that reads files through a glob or a walk declares the paths it reads in a `READ_SET`
at the top level of its module: a tuple of patterns in jmerge's syntax, as `Paths:` takes them.
A module of the tests that globs for the tests that import it declares one the same way. A
changed path that a pattern of the read set matches selects the test files whose read set it is,
or that import such a module, and the summary counts them with the names.
`testing/tests/test_cross_cutting.py` fails on a test that reads the tree so with neither a
read set nor a place on the `Cross-cutting:` list.

A model check, a test that runs TLC for minutes, runs only where the change reaches what it
checks. `MODEL_CHECKS` names each one with the paths that run it: the spec or the charts it
checks and the scripts that run TLC. Each file of a `src/` that a `.tla` file under those
folders cites, as the code it models, runs it too, and so does an edit to the test itself. No
other rule selects these tests, though nearly every change reaches them through an import or
a name. Main's full run and the nightly run them whatever changed.

A test file that no change to any other path selects is owned by no rule: it imports nothing,
spells no path and is on no list. A change it reads in some other way (a glob, a walk) would merge
with it unrun. So every change also runs each such test, the catch-all, and the summary counts
it with the cross-cutting tests.

A change of the tests alone runs a narrow check. Where every changed path is a module of a
folder of tests that the head still holds (a test file, a helper of the tests or a `conftest.py`),
the selection is the changed test files, the model checks they reach and the tests that import
or name a helper they changed: no feature's tests, no cross-cutting tests, no catch-all and no
test that failed on main. Such a change alters no code but the tests', and main's full run
catches what a narrow check misses. A change that also touches a fixture, deletes a file or
touches any path outside the tests selects by all the rules above.

It prints `all` when a changed path is one that every test depends on, and never for the size of
what it selected: a selection of nearly every test file still names its files, and main's full
run catches what a selection misses. Those paths are `pyproject.toml`, `uv.lock` and the root
`conftest.py`. They are also this script, the `Makefile` and `.github/workflows/check.yml`,
since a pull request's check picks and runs its tests by its own new version of them: a change
that made the script pick fewer tests would otherwise pick fewer for itself. They also include
each plugin of `testing/` that the root `conftest.py` names in `pytest_plugins` (as
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
selection `all`, and it is `-` otherwise. A collector reads that line. Last, after a blank line,
a folded block holds the selection's list: a line for each selected test file, with the causes
that selected it, comma-separated (`imports`, `names`, `features`, `cross-cutting`, `models`,
`catch-all`, `failed-on-main`), or the one line `all forced-by=<path>`. With `$GITHUB_OUTPUT`
set, it gives the step the output `selection`, `all` or `some`: the check workflow leaves the
tree's marker on a pass of `all`. It also gives `files`, `all` or how many test files it
printed, and `forced_by`, the path that made it `all` or nothing: the check notices both to
`jbus ci`, which keeps them in ci.jsonl as `selection` and `reason`. With `$SELECTED` set as
well, it writes the selection's list to that file too, which the check keeps as an artifact,
so a test a pull request did not run can be traced to the selection that left it out: only
beside `$GITHUB_OUTPUT`, which the suite's fixtures clear, so a test that runs the script in
the check's own environment leaves the step's list alone.

`select_tests.py --parts <n> <base> <head>` selects the same way, then hands the selection to
`<n>` parts that run side by side, as the check workflow's job `select` does for its eight. It
collects the selection with pytest, as `make test` does (`-m "not browser"`), in up to
`COLLECTORS` processes at once, each a run of whole files (or, for `all`, of the `testpaths`
folders), and deals out the test files, slowest first, each to the part that would end soonest
so far
(`testing/shard.py`'s split, over each file's tests summed from `testing/shard-times.tsv`, and
its slowest test, which no part ends before). So a part collects only its own files. A file
whose tests sum past a part's share is cut by test into the fewest pieces that each fit a share,
and each part that holds a piece gets the file and the word `--shard-tests=<keys>`, which runs
only those. With `$GITHUB_OUTPUT` set it gives the step the outputs `part1` to `part<n>`, each
a part's words, space-separated, or `none` for a part the selection left empty, and the summary
gets one more line: `parts: <n> of <tests> tests in <files> files, <s> s of test time each`,
from the least to the most. A selection that collects no test fails, as `make test` fails on
one. In the selection's list each line then ends `part=<k>`, the part that runs the file (`-`
for a file that collects no test, and the parts, comma-separated, for a file cut by test), and
an `all` lists every file of the suite with its part, after its first line. This form imports
pytest, so it runs after `uv sync`, as `uv run python3 scripts/select_tests.py --parts 8 HEAD^1
HEAD`.

`select_tests.py --part guards <base> <head>` prints only the guards of the selection: the
cross-cutting tests, the catch-all and the changed test files. `--part rest` prints the rest of
it, the files the rules reached through imports, names and features alone. Where the selection
is `all`, `--part guards` still prints those guards, never `all`, and `--part rest` prints `all`.
`jmerge` runs the guards on a pull request's tree merged over its base (`merged-tree-guards`).

`select_tests.py --part touched <base> <head>` prints the test files the change itself adds or
edits, each one the check runs, and never `all`: a change that selects every test still names
its own. It needs no selection, so it is quick. They are the desk's check, with the lint (the
crew's check block, features/crew/do-the-task.md, runs each file alone in the short lane), and
CI's check runs the rest of the selection.

`select_tests.py --within <list> <base> <head>` prints, of the test files a list names (a file,
or a folder of tests that ends in `/`), the ones the change reaches on a Mac: the macOS job reads
`testing/macos-quick.txt` so. It selects by the same rules but for two. An import reaches a test
only from a changed module of the tests, or of one whose text names Darwin (`DARWIN`): nearly
every test imports the CLI of a feature, so through any other module a change would reach nearly
the whole list, though its code runs the same on a Mac. And the tests that read the whole tree,
cross-cutting and the catch-all, do not count, since Linux runs them. It prints `all` when a
changed path is one every test depends on, or the list itself. It writes nothing to the
summary or the outputs. `--within <list> --strict <base> <head>` prints a part of that: a
module counts only where the diff's lines, in its base or its head, fall in a function that asks
for Darwin in code (`sys.platform`, `platform.system`, the string `darwin`, a name such as
`on_darwin`), not in a docstring or a comment; a file that is no Python counts where its text
names Darwin. A name reaches a test only from a changed path of the tests or one that counts, as
an import does, a feature's paths reach none of its tests, and only `EVERY_RUN`, which changes
every run, and the list itself print `all`: the rest of what every test depends on, such as the
fixtures, the Makefile and check.yml, reaches the tests that import or name it. A pull request's
macOS job selects so, and the run on each merge commit into main runs the whole `--within`.

Every test that failed on main in the last 30 days, and that main has not passed since, runs on each
pull request's check, whatever the rules select: timing tests that no pull request reached broke
main in 8 of the audit's 15 reds. `$FAILED_ON_MAIN` names them, space-separated, and the selection
adds each one that is a test file the check runs. The summary then gets one more line: `failed on
main: <n> test files, <k> added to the selection: <the files>`, the files the rules had not selected
already. Where the variable is not set, as on a desk, the selection and the summary are what the
rules make.

`select_tests.py --failed-on-main <days> <kept>` prints those test files, sorted and one per line:
the files a `FAILED` or `ERROR` line of pytest's names in the log of a red job of a push's run of
`check.yml` on main, created in the last `<days>` days, with every attempt of a run that was run
again, and that no later green run of main in those days has passed. A green run ran the whole
suite, a rerun that passed is one, and runs are ordered by id: GitHub numbers them as they are
created, so a green run of an older commit that ends after a red one passes nothing of it. A test
that fails and then passes on main drops out at the first green run after its failure. It reads
GitHub's REST API at `$GITHUB_API_URL` for `$GITHUB_REPOSITORY` with `$GITHUB_TOKEN`, and fails,
naming the answer, where GitHub refuses. A completed job and its log never change, so the JSON file
`<kept>` keeps the red jobs of each run's attempt and the files each one's log named, for the runs
still in the window. GitHub gives a filtered list of runs 1,000 at most, and main has more in a
month, so the lookup lists a day at a time. It keeps each day's red runs and newest green run too,
and lists again only the last `SETTLED` days, where a rerun of main still lands: a lookup with the
file reads about 4 lists. A rerun of a run older than that is missed. It reads the days, the job
lists and the logs `READS` at a time. Storage holds no log for some red jobs, and such a job names
no test.

The diff is two-dot. So for a pull request, `<base>` is where it branched from main (`git
merge-base`) or the parent of its merge commit. A base that main has moved past adds main's own
changes to the diff, which selects more tests and never fewer.
"""

import ast
import glob
import hashlib
import json
import math
import os
import pickle
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from tempfile import NamedTemporaryFile
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
SCRIPTS = "scripts"
PATHS = ("features/*/spec", "features/skill-library/skills/statechart/scripts")
"""The folders a test puts on `sys.path` and imports from by name. A test that loads a file by
its path, as the skill-cut eval's test does, puts no folder here."""
STATECHART = (
    "features/skill-library/skills/statechart/",
    "features/skill-library/tests/statechart/",
    "features/skill-library/tests/statechart_support.py",
)
MODEL_CHECKS = {
    "features/jmerge/tests/test_flow_spec.py": (
        "features/jmerge/spec/",
        "features/skill-library/skills/statechart/scripts/",
    ),
    "features/skill-library/tests/test_statechart_runs.py": STATECHART,
    "features/skill-library/tests/test_statechart_specs.py": STATECHART,
}
"""The model checks, each a test file that runs TLC for minutes, and the paths, in jmerge's
syntax, whose change runs it on a pull request's check: the spec or the charts it checks and
the scripts that run TLC. Each file of a `src/` that a `.tla` file under those folders cites,
as the code it models, runs it too, and so does a change to the test file itself. Nearly every
change reaches these tests through an import or a name, so this table alone selects them.
Main's full run and the nightly run them whatever changed."""
CITED = re.compile(r"features/[\w-]+/src/[\w/]+\.py")
EVERY_RUN = ("pyproject.toml", "uv.lock", "conftest.py")
"""The files that change every run of the tests, on a Mac too: the dependencies and the root
`conftest.py`, which loads the plugins. A change to one selects `all`, with `strict` too."""
EVERYTHING = (
    *EVERY_RUN,
    "scripts/select_tests.py",
    "Makefile",
    ".github/workflows/check.yml",
)
BACKTICKED = re.compile(r"`([^`]+)`")
DARWIN = re.compile(r"[Dd]arwin|sys\.platform|platform\.system")
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LABEL = re.compile(r"[A-Z][\w-]*:")
BROWSER = re.compile(r"^pytestmark\s*=.*\bpytest\.mark\.browser\b", re.M)
WORDS = re.compile(r"[\s/\\'\"`:=,()\[\]{}*|<>;]+")
DECLARED = "READ_SET"
CHECKING = ("TYPE_CHECKING", "typing.TYPE_CHECKING")
BY_NAME = {"import_module", "__import__"}
SKILL_INDEX = "testing.paths.skills"
SKILL_SPOTS = ("skills/*/SKILL.md", "features/*/SKILL.md", "features/*/skills/*/SKILL.md")
INCLUDE = re.compile(r"read `\$T/\.\./skills/([^/`]+)/([^/`]+\.md)` now")
COLLECTORS = 8
"""The most pytest processes `node_ids` collects in at once, each a run of the files: a hosted
runner's 4 cores collect a selection in about a third of the time one process takes."""
KEPT = "select_tests.facts"
"""The file in the repo's git directory that keeps each module's `facts` from one run to the
next, by its path and a hash of its text: a module that has not changed is not parsed again."""
FAILED_ON_MAIN = "FAILED_ON_MAIN"
WORKFLOW = "check.yml"
PER_PAGE = 100
READS = 8
SETTLED = 4
FAILING = re.compile(r"^(?:\S+Z )?(?:FAILED|ERROR) (\S+?\.py)(?:::|\s|$)", re.M)
COLOR = re.compile(r"\x1b\[[0-9;]*m")


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


@cache
def cross_cutting():
    return listed((ROOT / CROSS).read_text(), "Cross-cutting")


@cache
def models():
    """Each model check, with the patterns of the paths that select it: its own path, its row
    of `MODEL_CHECKS`, and each file of a `src/` that a `.tla` file under a folder of that row
    cites."""
    found = {}
    for test, patterns in MODEL_CHECKS.items():
        specs = [
            one
            for pattern in patterns
            if pattern.endswith("/")
            for one in ROOT.glob(f"{pattern}**/*.tla")
        ]
        cited = {cite for spec in specs for cite in CITED.findall(spec.read_text(encoding="utf-8"))}
        found[test] = (test, *patterns, *sorted(cited))
    return found


def owns(patterns, path):
    return any(ready().protects(pattern, path) for pattern in patterns)


def of_tests(path):
    """Whether a path is the tests' own: under `testing/tests/`, a feature's `tests/`, or
    `testing/`."""
    return bool(TESTS.match(path)) or path.startswith(SHARED)


@cache
def ours():
    """The modules of the tests' own (`of_tests`), by name."""
    return frozenset(name for name, path in modules().items() if of_tests(path))


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
    their names from that folder. The fixtures' folders hold no module. A test may put `scripts/`
    on `sys.path`, so each package there, as `scripts/jtrees/`, takes its name from that folder.
    A lone script there is no module: a test loads it from its path. Each folder of `PATHS` is a
    root too, and a file there whose name is no identifier, as `FlowToday.map.py`, is no module."""
    roots = [
        ROOT / "src",
        *sorted(ROOT.glob("features/*/src")),
        ROOT / SHARED_TESTS,
        *sorted(ROOT.glob("features/*/tests")),
        ROOT / SCRIPTS,
        *sorted(folder for pattern in PATHS for folder in ROOT.glob(pattern)),
        ROOT,
    ]
    found = {}
    for root in roots:
        if root == ROOT:
            files = (root / SHARED).rglob("*.py")
        elif root == ROOT / SCRIPTS:
            files = (
                one for init in root.glob("*/__init__.py") for one in init.parent.rglob("*.py")
            )
        else:
            files = root.rglob("*.py")
        for path in sorted(files):
            named = path.relative_to(ROOT).as_posix()
            if root == ROOT and not plumbing(named):
                continue
            parts = list(path.relative_to(root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            if not all(part.isidentifier() for part in parts):
                continue
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


def declared(tree):
    """The patterns of a module's `READ_SET`: the paths it reads through a glob. This raises
    `Unread` if the read set is not a tuple or a list of strings jmerge can read as patterns."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == DECLARED:
            items = getattr(node.value, "elts", None)
            if not isinstance(node.value, (ast.Tuple, ast.List)) or not all(
                isinstance(one, ast.Constant) and isinstance(one.value, str) for one in items
            ):
                raise Unread(f"{DECLARED} is not a tuple of strings: {ast.unparse(node.value)}")
            patterns = tuple(one.value for one in items)
            try:
                return ready().patterns_of("\n".join(patterns))
            except ValueError as error:
                raise Unread(f"{DECLARED}: {error}") from error
    return ()


def checking(node):
    """Whether a node is an `if TYPE_CHECKING:`, whose body only a type checker reads."""
    return isinstance(node, ast.If) and ast.unparse(node.test) in CHECKING


def walk(node):
    """The nodes of a tree, in the order `ast.walk` gives them, as a list: about twice as quick
    as `ast.walk`, which the script calls for each module and for each of its functions."""
    found = [node]
    for one in found:
        for field in one._fields:
            value = getattr(one, field, None)
            if isinstance(value, ast.AST):
                found.append(value)
            elif isinstance(value, list):
                found += [item for item in value if isinstance(item, ast.AST)]
    return found


def named(node):
    """The names a node and the nodes in it name: `f` of `f()`, of `x.f` and of `partial(f)`."""
    return {
        getattr(one, "attr", getattr(one, "id", ""))
        for one in walk(node)
        if isinstance(one, (ast.Name, ast.Attribute))
    }


def at_import(tree):
    """The nodes that run when the module is imported: all but the bodies of its functions."""
    todo = list(tree.body)
    while todo:
        node = todo.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            todo += [*getattr(node, "decorator_list", ()), *node.args.defaults]
            todo += [one for one in node.args.kw_defaults if one]
        else:
            todo += ast.iter_child_nodes(node)


def by_name(tree, nodes):
    """`(on import, holders, targets)`: whether the module imports by name when it is imported,
    the names that import by name when what they hold runs, and the modules its calls name in a
    string, as `import_module("a.b")` does.

    A holder is a function that imports by name or names a holder, as `partial(f)` does, since it
    may call it later. A name the module binds on import to a value that names a holder is a
    holder too: whoever reads the registry `VERBS = (Verb(..., f),)` may call `f`. The module
    imports by name on import when it calls a holder then, or decorates with one. A holder that is
    a method, or that a decorator may register, is called where no import names it, so the module
    counts as importing by name on import then too. `nodes` are the tree's, as `walk` gives
    them. A module that names no function of `BY_NAME` anywhere has none of the three."""
    if not any(
        isinstance(node, (ast.Name, ast.Attribute))
        and getattr(node, "attr", getattr(node, "id", "")) in BY_NAME
        for node in nodes
    ):
        return False, frozenset(), frozenset()
    functions = [
        node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    holds = {}
    for one in functions:
        holds.setdefault(one.name, set()).update(named(one) - {one.name})
    records = {
        node.name
        for node in nodes
        if isinstance(node, ast.ClassDef)
        and "dataclass" in set().union(*map(named, node.decorator_list))
    }
    run, decorated = set(), set()
    for node in at_import(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
            for target in getattr(node, "targets", [getattr(node, "target", None)]):
                for name in named(target):
                    holds.setdefault(name, set()).update(named(node.value))
        elif isinstance(node, ast.Call):
            run |= named(node.func)
            if getattr(node.func, "id", None) not in records:
                given = [*node.args, *(one.value for one in node.keywords)]
                run |= set().union(*map(named, given))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            run |= set().union(*map(named, node.decorator_list))
            if node.decorator_list:
                decorated.add(node.name)
    holders = {name for name, held in holds.items() if held & BY_NAME}
    while more := {name for name, held in holds.items() if held & holders} - holders:
        holders |= more
    methods = {
        one.name
        for node in nodes
        if isinstance(node, ast.ClassDef)
        for one in node.body
        if isinstance(one, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    targets = {
        node.args[0].value
        for node in nodes
        if isinstance(node, ast.Call) and named(node.func) & BY_NAME and node.args
        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
    }
    on_import = bool(run & (BY_NAME | holders) or (methods | decorated) & holders)
    return on_import, frozenset(holders), frozenset(targets)


def bound(nodes):
    """Each name the module's imports bind, with the dotted name it is bound to: `a` for
    `import a.b`, `a.b` for `import a.b as b` and for `from a import b`. A star import binds
    names this script does not read, so `from a import *` is kept as `*a`, bound to `a`. `nodes`
    are a tree's, as `ast.walk` gives them."""
    found = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for alias in node.names:
                if alias.name == "*":
                    found[f"*{node.module}"] = node.module
                else:
                    found[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return found


def dotted(node, names):
    """The dotted name a node spells through the names the imports bind, or `None`."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and (root := dotted(node.value, names)):
        return f"{root}.{node.attr}"
    return None


def folder(before):
    """Whether the part of a chain of `/` after `before`, its previous part, is a folder: a part
    after a string other than `bin`. A part after `bin`, or after a part that is no string, as in
    `stub / "jbus"`, may be a command."""
    return bool(before) and before[0] not in (None, "bin")


def read(tree, nodes):
    """Return what this script reads from a module's tree: the names the module imports, the
    words of its string constants, where it imports by name (`by_name`), the names of its
    functions' arguments, the paths it spells, its read set, the dotted names it names through
    its imports, and those imports (`bound`). A name no import binds may come from a star import,
    so it is named under each module the module star-imports. An import in an `if TYPE_CHECKING:`
    is no import: it never runs. A string that is a `folder` of a chain of `/` is spelled with the
    chain, and not as a path of its own: the `jbus` of `home / ".config" / "jbus"` is a folder,
    not the package run in a process. `nodes` are the tree's, as `walk` gives them."""
    names, words, args, paths, calls = set(), set(), set(), set(), set()
    checked = {
        id(one) for node in nodes if checking(node) for part in node.body for one in walk(part)
    }
    chains = [
        node for node in nodes if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]
    folders = {id(node.left) for node in chains} | {
        id(node.right) for node in chains if folder(spelled(node)[-2:-1])
    }
    imports = bound(nodes)
    stars = [module for local, module in imports.items() if local.startswith("*")]
    for node in nodes:
        if isinstance(node, ast.Import) and id(node) not in checked:
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if id(node) not in checked:
                names.add(node.module)
                names |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, (ast.Name, ast.Attribute)):
            if name := dotted(node, imports):
                calls.add(name)
            elif isinstance(node, ast.Name):
                calls |= {f"{module}.{node.id}" for module in stars}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            words |= {node.value, *WORDS.split(node.value)}
            if id(node) not in folders:
                paths.add(tuple(spelled(node)))
        elif isinstance(node, ast.arg):
            args.add(node.arg)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            paths.add(tuple(spelled(node)))
    return (
        names,
        words,
        by_name(tree, nodes),
        args,
        paths,
        declared(tree),
        frozenset(calls),
        imports,
    )


def parents(name):
    parts = name.split(".")
    return {".".join(parts[:end]) for end in range(1, len(parts) + 1)}


@cache
def facts():
    """Each module, with `(read, defined, members)`: what `read` finds in its source, the
    fixtures it defines (`defines`), and for a module of the tests what its top-level names
    hold (`holding`), from one parse of its file, or from `KEPT` where its text is the same as
    when they were kept. No tree is kept: a cache of the trees of every module makes each
    collection of garbage walk them, and the script slower."""
    salt, where = kept()
    old = load(where, salt) if where else {}
    found, new = {}, {}
    for name, path in modules().items():
        text = (ROOT / path).read_text()
        digest = hashlib.sha1(text.encode()).digest()
        if path in old and old[path][0] == digest:
            found[name] = old[path][1]
        else:
            try:
                tree = ast.parse(text)
            except SyntaxError as error:
                raise Unread(f"{path}: {error}") from error
            nodes = walk(tree)
            mine = defines(tree)
            one = read(tree, nodes)
            held = holding(tree, nodes, mine, one[7]) if of_tests(path) else None
            found[name] = (one, mine, held)
        new[path] = (digest, found[name])
    if where and (new.keys() != old.keys() or any(new[one][0] != old[one][0] for one in new)):
        keep(where, salt, new)
    return found


def kept():
    """`(salt, path)`: what each module's facts rest on besides its own text (this script,
    jmerge's reader of patterns, the skills' names and the Python), and the path of `KEPT`, or
    `None` outside a git repo."""
    ran = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True
    )
    where = None if ran.returncode else ROOT / ran.stdout.strip() / KEPT
    readers = [ROOT / "src", *sorted(ROOT.glob("features/*/src"))]
    patterns = [one / "jmerge" / "ready.py" for one in readers]
    salt = hashlib.sha1(Path(__file__).read_bytes())
    salt.update(next((one.read_bytes() for one in patterns if one.is_file()), b""))
    salt.update("\n".join([sys.version, *sorted(skills())]).encode())
    return salt.digest(), where


def load(where, salt):
    """The facts `KEPT` holds by each module's path, with the hash of its text, or none where
    the file is missing, unreadable or kept under another salt."""
    try:
        with open(where, "rb") as file:
            held = pickle.load(file)
    except Exception:
        return {}
    return held[1] if isinstance(held, tuple) and held[0] == salt else {}


def keep(where, salt, held):
    """Write `KEPT` whole, in place of the old one at once, or leave it: a run that cannot write
    it selects the same."""
    try:
        with NamedTemporaryFile(dir=where.parent, prefix=f"{KEPT}.", delete=False) as file:
            try:
                pickle.dump((salt, held), file, protocol=pickle.HIGHEST_PROTOCOL)
            except BaseException:
                os.unlink(file.name)
                raise
        os.replace(file.name, where)
    except OSError:
        pass


@cache
def sources():
    """Each module, with what `read` finds in its source."""
    return {name: one[0] for name, one in facts().items()}


@cache
def edges():
    """Each module, with the modules it imports. A test may spell the name of a package in a `src/`
    folder. The script then counts the test as running that package in a process of its own, and so
    as importing every module of the package.

    A module that imports by name imports every module under its directory, but only when that code
    runs. So the module itself imports them when it imports by name on import, or when it is a
    module of the tests, whose functions pytest runs. Otherwise each module that names, through its
    imports, a function of it that imports by name imports them: by a name, or by a string, as
    `getattr(module, "found")` does. Whoever imports that module inherits the edge. A module a
    by-name call names in a string, as `import_module("a.b")` does, is imported the same way, even
    when it lies outside the directory."""
    known = modules()
    packages = {}
    for path in known.values():
        if at := SOURCE.match(path):
            package = path[at.end() :].split("/")[0]
            packages[package] = path[: at.end()] + package
    held = {}
    for name, (_, _, (_, holders, _), _, _, _, _, _) in sources().items():
        for one in holders:
            held.setdefault(f"{name}.{one}", set()).add(name)
    held = exported(held)
    found = {}
    for name, (names, words, (loaded, holders, _), _, paths, _, calls, _) in sources().items():
        reached = set().union(*map(parents, names)) & known.keys()
        itself = {name} if loaded or holders and of_tests(known[name]) else set()
        uses = calls | {
            one
            for one in held
            if one.rpartition(".")[0] in names and one.rpartition(".")[2] in words
        }
        for loader in itself.union(*(held.get(one, ()) for one in uses)):
            below = Path(known[loader]).parent.as_posix() + "/"
            reached |= {other for other, path in known.items() if path.startswith(below)}
            reached |= set().union(*map(parents, sources()[loader][2][2])) & known.keys()
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


def exported(held):
    """`held`, each holder's dotted name with the modules whose code it runs, and with it each
    name a module binds to a holder: `reg.found` for `from reg.kinds import found` in `reg`, and
    for `from reg.kinds import *` there. A test that calls a holder by the name of a package that
    re-exports it runs the holder all the same."""
    held = {key: set(loaders) for key, loaders in held.items()}
    while True:
        more = {}
        for name, one in sources().items():
            for local, target in one[7].items():
                if local.startswith("*"):
                    pairs = [
                        (f"{name}.{key.rpartition('.')[2]}", key)
                        for key in held
                        if key.rpartition(".")[0] == target
                    ]
                else:
                    pairs = [(f"{name}.{local}", target)] if target in held else []
                for key, source in pairs:
                    if not held[source] <= held.get(key, set()):
                        more.setdefault(key, set()).update(held[source])
        if not more:
            return held
        for key, loaders in more.items():
            held.setdefault(key, set()).update(loaders)


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


@cache
def imported(name):
    """The modules a module imports, through any chain, and the module itself."""
    found, todo = set(), [name]
    while todo:
        one = todo.pop()
        if one not in found:
            found.add(one)
            todo += edges()[one]
    return frozenset(found)


@cache
def testers():
    """Each module, with the test files that import it, through any chain, or are it: what
    `test_files(importers([module]))` gives, for every module at once."""
    found = {}
    for name, path in modules().items():
        if TEST.fullmatch(path):
            for one in imported(name):
                found.setdefault(one, set()).add(path)
    return found


def test_files(names):
    return {modules()[name] for name in names if TEST.fullmatch(modules()[name])}


@cache
def reached(name):
    """A test module and the modules of the tests it imports, through any chain."""
    todo, seen = [name], set()
    while todo:
        one = todo.pop()
        if one not in seen and one in ours():
            seen.add(one)
            todo += edges()[one]
    return frozenset(seen)


@cache
def skills():
    """Each skill's folder by its name, from the root, as `testing.paths.skills` finds them."""
    found = (path.parent for spot in SKILL_SPOTS for path in ROOT.glob(spot))
    return {folder.name: folder.relative_to(ROOT).as_posix() for folder in sorted(found)}


def members(name):
    """`holding` of a module of the tests."""
    return facts()[name][2]


def holding(tree, nodes, mine, imports):
    """Each name a module binds at its top level, with what its code holds: `(words, names,
    dotted, asks)`, the skills its strings name, the module's own names it reads and does not
    bind itself (`f` of `f()`, not `x` of `x = 1` nor `f` of `x.f`), the dotted names it names
    through the imports, and, for a test or a fixture, the fixtures it asks for by its
    arguments. A name an import binds holds the dotted name it is bound to. The key `None` holds
    the code that runs on import: each statement that binds no name, and each assignment that
    calls something. A docstring is no code, and a string that is a part of a chain of `/`, as
    the `"home"` of `state / "home"`, is a folder and names no skill. `nodes` are the tree's, as
    `walk` gives them, `mine` the fixtures it defines and `imports` what its imports bind
    (`bound`)."""
    stars = [module for local, module in imports.items() if local.startswith("*")]
    unread = set()
    for node in nodes:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                unread.add(id(node.body[0].value))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            unread |= {id(node.left), id(node.right)}
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        words, dots, loaded, own, calls = set(), set(), set(), set(), False
        for one in walk(node):
            if isinstance(one, ast.Constant) and isinstance(one.value, str):
                if id(one) not in unread:
                    words |= {one.value, *WORDS.split(one.value)} & skills().keys()
            elif isinstance(one, ast.arg):
                own.add(one.arg)
            elif isinstance(one, ast.Call):
                calls = True
            if isinstance(one, (ast.Name, ast.Attribute)):
                if dot := dotted(one, imports):
                    dots.add(dot)
                elif isinstance(one, ast.Name):
                    dots |= {f"{module}.{one.id}" for module in stars}
            if isinstance(one, ast.Name):
                (loaded if isinstance(one.ctx, ast.Load) else own).add(one.id)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keys = {node.name}
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            keys = set().union(*map(named, targets)) | ({None} if calls else set())
        else:
            keys = {None}
        asks = set()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name.startswith("test") or node.name in mine
        ):
            asks = {one.arg for one in node.args.args}
        for key in keys:
            held = found.setdefault(key, (set(), set(), set(), set()))
            for into, more in zip(held, (words, loaded - own - {key}, dots, asks), strict=True):
                into |= more
    for local, target in imports.items():
        if not local.startswith("*"):
            found.setdefault(local, (set(), set(), set(), set()))[2].add(target)
    return found


@cache
def uses(at):
    """`(skills, dotted)` of the code a top-level name of a module of the tests runs, `at` as
    `(module, name)` (`members`): its own, and through each name it uses, in that module or
    through an import in another, and each fixture it asks for, of its module, a `conftest`
    above it or a plugin."""
    todo, seen, words, dots = [at], set(), set(), set()
    while todo:
        one = todo.pop()
        if one in seen or one[1] not in members(one[0]):
            continue
        seen.add(one)
        found, names, through, asks = members(one[0])[one[1]]
        words |= found
        dots |= through
        todo += [(one[0], other) for other in names]
        for ask in asks:
            todo += [(module, ask) for module in givers(one[0]) if ask in defined(module)][:1]
        for dot in through:
            module, _, member = dot.rpartition(".")
            if module in ours():
                todo.append((module, member))
    return frozenset(words), frozenset(dots)


@cache
def givers(name):
    """Where a fixture a module of the tests asks for comes from, nearest first: the module, the
    `conftest` of each folder above it, and the plugins."""
    return [name, *sorted(conftests(name) & modules().keys(), reverse=True), *plugins()]


@cache
def reaches(name):
    """The skills the code of a test module names where that code reads skills through
    `testing.paths.skills()`: for each top-level name of its own, and for the code each module of
    the tests it imports runs on import, the skills what it runs names (`uses`), where that
    reads skills."""
    starts = [(name, key) for key in members(name)] + [(one, None) for one in reached(name)]
    found = [uses(one) for one in starts]
    return frozenset().union(*(words for words, dots in found if SKILL_INDEX in dots))


@cache
def spells(name):
    """The paths a test module spells, and the test modules it imports. Where code of the test
    reads skills through `testing.paths.skills()`, a word of that code (`reaches`) that is a
    skill's name spells that skill's `SKILL.md`: `block("home", …)` reads the home skill so. A
    name of a skill elsewhere in a module it imports spells nothing: `test_home_thread` names
    four skills, and a test that takes only its `git` reads none of them."""
    paths = frozenset().union(*(sources()[one][4] for one in reached(name)))
    return paths | {(*skills()[word].split("/"), "SKILL.md") for word in reaches(name)}


@cache
def read_sets():
    """Each test file, with the patterns of its read set and of the read sets of the modules of
    the tests it imports."""
    found = {}
    for name, path in modules().items():
        if not TEST.fullmatch(path):
            continue
        if patterns := {pattern for one in reached(name) for pattern in sources()[one][5]}:
            found[path] = patterns
    return found


@cache
def globbed():
    """Each pattern of a read set, with the test files whose read set holds it: the read sets
    share most of their patterns."""
    found = {}
    for test, patterns in read_sets().items():
        for pattern in patterns:
            found.setdefault(pattern, set()).add(test)
    return found


def globbers(path):
    """The test files whose read set matches this path."""
    return set().union(*(tests for pattern, tests in globbed().items() if owns([pattern], path)))


def inside(parts, spelling):
    """Whether `parts` are in `spelling`, one after the other."""
    return any(spelling[at : at + len(parts)] == parts for at in range(len(spelling)))


@cache
def tracked():
    ran = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if ran.returncode:
        raise Unread(f"git ls-files failed: {ran.stderr.strip()}")
    return frozenset(ran.stdout.splitlines())


@cache
def endings():
    """How many tracked files end in each run of their last parts: `a/b/c.md` ends in `c.md`,
    `b/c.md` and `a/b/c.md`."""
    found = {}
    for one in tracked():
        parts = one.split("/")
        for start in range(len(parts)):
            ending = "/".join(parts[start:])
            found[ending] = found.get(ending, 0) + 1
    return found


def called(path):
    """The parts of a path a test spells to name it: its file name, and with it the directories
    above it until no other file has the same ending."""
    parts = path.split("/")
    itself = int(path in tracked())
    for start in range(len(parts) - 1, -1, -1):
        if endings().get("/".join(parts[start:]), 0) == itself:
            return tuple(parts[start:])
    return tuple(parts)


@cache
def spelled_by():
    """The test files that spell each run of consecutive parts of a spelled path. It gives the
    result of `inside` for every test file at once, and reads each file once."""
    spellers = {}
    for name, path in modules().items():
        if TEST.fullmatch(path):
            for spelling in spells(name):
                spellers.setdefault(spelling, set()).add(path)
    found = {}
    for spelling, paths in spellers.items():
        for start in range(len(spelling)):
            for end in range(start + 1, len(spelling) + 1):
                found.setdefault(spelling[start:end], set()).update(paths)
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
    for node in walk(tree):
        if isinstance(node, ast.Import):
            bound |= {(a.asname or a.name).split(".")[0]: a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            bound |= {a.asname or a.name: node.module for a in node.names}
    return {local: name for local, name in bound.items() if of_tests(modules().get(name, ""))}


@cache
def plugins():
    """The modules the root `conftest.py` names in `pytest_plugins`, which every test loads."""
    for node in ast.parse((ROOT / "conftest.py").read_text()).body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "pytest_plugins":
            return tuple(one.value for one in node.value.elts if modules().get(one.value))
    return ()


def used(node, bound):
    """The modules that a node uses, from `bound`, which maps each name to the module it is
    bound to."""
    return {bound[one.id] for one in walk(node) if isinstance(one, ast.Name) and one.id in bound}


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


def defined(name):
    """The fixtures a module defines at its top level (`defines`)."""
    return facts()[name][1]


def defines(tree):
    """The fixtures a module's tree defines at its top level: a test that asks for one of them
    by name gets its own, and not a plugin's."""
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
    fixtures = conftest()[1]
    hit = {name for name, one in reaches_through().items() if module in one}
    while more := {name for name, (_, asks) in fixtures.items() if asks & hit} - hit:
        hit |= more
    return {test for test, asks in askers().items() if hit & asks}


@cache
def reaches_through():
    """Each fixture of a plugin, with the modules it reaches through those it uses: each of
    them, and what each imports through any chain."""
    return {
        name: frozenset().union(*map(imported, used)) for name, (used, _) in conftest()[1].items()
    }


@cache
def askers():
    """Each test file, with the names it may ask a plugin for: its arguments and its words, but
    the fixtures it has of its own."""
    return {
        modules()[name]: (args | words) - own(name)
        for name, (_, words, _, args, _, _, _, _) in sources().items()
        if TEST.fullmatch(modules()[name])
    }


@cache
def runs(test):
    """Whether the check runs this test file: it is there, and it does not open a browser."""
    return (ROOT / test).is_file() and not opens_browser(test)


@cache
def opens_browser(test):
    """Whether the test file marks its whole module `browser`, which `make check-browser` runs
    and the check leaves out."""
    return bool(BROWSER.search((ROOT / test).read_text()))


def everywhere(path):
    return True


def ruled(changed, follows=everywhere, cross=True, strict=False):
    """`(tests, why)`: the sorted test files the rules select for the changed paths, or
    `["all"]`, and for each cause the sorted files it selected, or the path that forced
    `all`. An import reaches a test only from a changed path that `follows` holds for, and the
    cross-cutting tests count only with `cross`. With `strict` a name reaches a test only from
    such a path too, a feature's paths reach none of its tests, and only `EVERY_RUN` forces
    `all`: the rest of `shared()` reaches tests through its importers and names, as any path
    does."""
    ready()
    forcing = shared() & set(EVERY_RUN) if strict else shared()
    for path in changed:
        if path in forcing:
            return ["all"], {"forced-by": path}
    by_path = {path: name for name, path in modules().items()}
    found = {"imports": set(), "names": set(), "features": set()}
    for path in changed:
        counts = not strict or follows(path)
        if path in by_path:
            if follows(path):
                found["imports"] |= testers().get(by_path[path], set()) | asking(by_path[path])
            if of_tests(path) and counts:
                found["names"] |= readers(path)
        elif FIXTURES.match(path):
            if not (named := fixture_readers(path)):
                return ["all"], {"forced-by": path}
            if counts:
                found["names"] |= named
        else:
            if SOURCE.match(path) and follows(path):
                found["imports"] |= test_files(importers(users(path)))
            if counts:
                for one in {path} | includers(path):
                    found["names"] |= readers(one)
        if counts:
            found["names"] |= globbers(path)
    where = {} if strict else pages()
    for name in where:
        owned, listed_tests = features()[name]
        if any(owns(owned, path) for path in changed):
            found["features"] |= set(listed_tests)
        if where[name] in changed:
            found["features"] |= feature_tests(name)
    found["cross-cutting"] = set(cross_cutting()) if cross else set()
    for key in found:
        found[key] -= models().keys()
    found["models"] = {
        test for test, paths in models().items() if any(owns(paths, path) for path in changed)
    }
    present = {key: {one for one in tests if runs(one)} for key, tests in found.items()}
    return sorted(set().union(*present.values())), {
        key: sorted(one) for key, one in present.items()
    }


def collected():
    """The test files the check runs: each one there is, but the ones marked `browser`."""
    return {one for one in modules().values() if TEST.fullmatch(one) and runs(one)}


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


def tests_alone(changed):
    """Whether every changed path is a module of a folder of tests that is still there: a test
    file, a helper of the tests or a `conftest.py`. A fixture, a deleted file or a module of
    `testing/` outside its tests is not."""
    return bool(changed) and all(
        TESTS.match(path) and path.endswith(".py") and (ROOT / path).is_file() for path in changed
    )


def selection(changed, failed=()):
    """`(tests, why)`: the sorted test files the changed paths need, or `["all"]`, and for
    each cause the sorted files it selected, or the path that forced `all`. They are what the
    rules select, the test files no rule owns (`catch-all`), and the `failed` test files that
    the check runs. `why["added"]` lists the failed ones nothing else selected. A change of the
    tests alone selects only what its imports and names reach."""
    tests, why = ruled(changed)
    if tests == ["all"]:
        return tests, why
    if tests_alone(changed):
        narrow = sorted(set(why["imports"]) | set(why["names"]) | set(why["models"]))
        return narrow, {
            "imports": why["imports"],
            "names": why["names"],
            "models": why["models"],
            **{key: [] for key in ("features", "cross-cutting", "catch-all", "added")},
        }
    lone = unowned()
    chosen = set(tests) | lone
    added = set(failed) & collected() - chosen
    return sorted(chosen | added), {**why, "catch-all": sorted(lone), "added": sorted(added)}


DESK_PARTS = ("guards", "rest", "touched")


def touched(changed):
    """The test files of `changed` that the check runs: the desk's own share of a change."""
    return sorted(set(changed) & collected())


def guards(changed, tests):
    """Of a selection's `tests`, the ones a desk runs first and must pass: the cross-cutting
    tests, the catch-all and the changed test files. A selection of `["all"]` gives them all the
    same, never the whole suite, which outran jmerge's 600 s on a merged tree: CI's check of the
    pull request runs the rest."""
    first = set(cross_cutting()) | unowned() | set(changed)
    if tests == ["all"]:
        return sorted(first & collected())
    return sorted(set(tests) & first)


def desk_part(name, changed, tests):
    """The `guards` or the `rest` of a selection's `tests`. The rest of `["all"]` is `["all"]`."""
    if name == "guards":
        return guards(changed, tests)
    if tests == ["all"]:
        return tests
    return sorted(set(tests) - set(guards(changed, tests)))


def ask(path, gone=None, **query):
    """The answer GitHub's REST API gives to a GET of the repo's `path`, or `gone` where it
    answers 404 and `gone` is given. A log's answer is a redirect to storage that refuses the
    token, so the token goes to GitHub alone."""
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api}/repos/{os.environ['GITHUB_REPOSITORY']}/{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    request.add_unredirected_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            return answer.read()
    except urllib.error.HTTPError as error:
        if error.code == 404 and gone is not None:
            return gone
        sys.exit(f"select_tests.py: GitHub answered {error.code} to {path}: {error.read()[:200]!r}")
    except urllib.error.URLError as error:
        sys.exit(f"select_tests.py: GitHub did not answer {path}: {error.reason}")


def side_by_side(read, items):
    """`{item: read(item)}`, the reads made at once: each is a wait on GitHub."""
    with ThreadPoolExecutor(max_workers=READS) as pool:
        return dict(zip(items, pool.map(read, items), strict=True))


def red_runs(day):
    """The completed push runs of `WORKFLOW` on main created on a UTC `day`: `red`, the ones
    that failed or were run again, and `green`, the newest that passed, or `None`. Each is
    `<id>/<attempt>`, and `later` orders them. GitHub gives a filtered list 1,000 runs at most,
    and main has more in a month, so a day is listed at a time."""

    def page(number):
        return json.loads(
            ask(
                f"actions/workflows/{WORKFLOW}/runs",
                branch="main",
                event="push",
                status="completed",
                created=day,
                exclude_pull_requests="true",
                per_page=PER_PAGE,
                page=number,
            )
        )

    first = page(1)
    rest = [page(number) for number in range(2, -(-first["total_count"] // PER_PAGE) + 1)]
    runs = [run for one in (first, *rest) for run in one["workflow_runs"]]
    green = [f"{run['id']}/{run['run_attempt']}" for run in runs if run["conclusion"] == "success"]
    return {
        "red": sorted(
            {
                f"{run['id']}/{run['run_attempt']}"
                for run in runs
                if run["conclusion"] == "failure" or run["run_attempt"] > 1
            }
        ),
        "green": max(green, key=later, default=None),
    }


def later(run):
    """A run's place in time as `(id, attempt)`: GitHub numbers runs as they are created, so a
    larger id checked a later commit of main, and a rerun comes after the attempts before it."""
    return tuple(map(int, run.split("/")))


def named_in(log):
    """The test files a log's `FAILED` and `ERROR` lines of pytest's name."""
    return sorted(set(FAILING.findall(COLOR.sub("", log))))


def red_jobs(run):
    """The ids of the jobs that failed in any attempt of a run, given as `<id>/<attempt>`."""
    listed = ask(f"actions/runs/{run.split('/')[0]}/jobs", filter="all", per_page=PER_PAGE)
    return [str(job["id"]) for job in json.loads(listed)["jobs"] if job["conclusion"] == "failure"]


def logged(job):
    """The test files a job's log names. Storage holds no log for some red jobs, and such a
    job names none."""
    return named_in(ask(f"actions/jobs/{job}/logs", gone=b"").decode(errors="replace"))


def failed_on_main(days, kept_path):
    """The test files a red job of main's runs of the last `days` days named and no later green
    run of main has passed, sorted. A green run ran the whole suite, so a test it passed is red on
    main no more, and a rerun that passed counts as one, since its red jobs are an earlier
    attempt's. `kept` holds what earlier lookups read, and is left with the days, runs and jobs
    still in the window. The last `SETTLED` days are listed again, and an older one only when
    `kept` lacks it."""
    kept = {"days": {}, "runs": {}, "jobs": {}}
    if kept_path.is_file():
        kept |= json.loads(kept_path.read_text())
    today = datetime.now(UTC).date()
    window = [(today - timedelta(days=back)).isoformat() for back in range(days + 1)]
    listed = dict.fromkeys(window[:SETTLED])
    listed |= {day: kept["days"].get(day) for day in window[SETTLED:]}
    listed |= side_by_side(red_runs, [day for day, runs in listed.items() if runs is None])
    runs = {run: kept["runs"].get(run) for day in window for run in listed[day]["red"]}
    runs |= side_by_side(red_jobs, [run for run, jobs in runs.items() if jobs is None])
    red = sorted({job for jobs in runs.values() for job in jobs})
    jobs = {job: kept["jobs"].get(job) for job in red}
    jobs |= side_by_side(logged, [job for job, tests in jobs.items() if tests is None])
    kept_path.parent.mkdir(parents=True, exist_ok=True)
    kept = {"days": listed, "runs": runs, "jobs": jobs}
    kept_path.write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n")
    last = {}
    for run in sorted(runs, key=later):
        last |= {test: run for job in runs[run] for test in jobs[job]}
    greens = [day["green"] for day in listed.values() if day["green"]]
    if not greens:
        return sorted(last)
    passed = later(max(greens, key=later))
    return sorted(test for test, run in last.items() if later(run) > passed)


def told(tests, why, failed):
    """The summary's line on the tests that failed on main."""
    if tests == ["all"]:
        return f"failed on main: {len(failed)} test files, and the whole suite runs"
    added = why["added"]
    return f"failed on main: {len(failed)} test files, {len(added)} added to the selection" + (
        f": {' '.join(added)}" if added else ""
    )


def on_a_mac(path):
    """Whether a change to this path can run differently on a Mac: a path of the tests, or a
    file whose text names Darwin. The run on each merge commit selects so."""
    file = ROOT / path
    return (
        of_tests(path) or file.is_file() and bool(DARWIN.search(file.read_text(errors="replace")))
    )


def names_darwin(node):
    """Whether an AST node is code that asks for Darwin: `sys.platform`, `platform.system`, the
    string `darwin` itself, or a name that spells it, such as `on_darwin`. A docstring or a
    comment is none of these."""
    match node:
        case ast.Attribute(attr="platform", value=ast.Name(id="sys")):
            return True
        case ast.Attribute(attr="system", value=ast.Name(id="platform")):
            return True
        case ast.Constant(value="darwin" | "Darwin"):
            return True
        case ast.Name(id=name) | ast.Attribute(attr=name):
            return "darwin" in name or "Darwin" in name
        case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
            return "darwin" in name or "Darwin" in name
    return False


def darwin_spans(text):
    """The first and last line of each piece of a module's code that branches on Darwin: the
    innermost function that asks for Darwin, or, outside any function, the top-level statement
    that does. `None` where the text is no Python."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    spans = set()

    def walk(node, span):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            first = min([node.lineno, *(one.lineno for one in node.decorator_list)])
            span = (first, node.end_lineno)
        if names_darwin(node):
            spans.add(span)
        for child in ast.iter_child_nodes(node):
            walk(child, span)

    for statement in tree.body:
        walk(statement, (statement.lineno, statement.end_lineno))
    return sorted(spans)


def branches_on_darwin(path, edit=None):
    """Whether a change to a module runs code that branches on Darwin: a line `edit` touched,
    before or after, falls in one of `darwin_spans`. Without an `edit` the whole file counts as
    changed. A file that is no Python counts when its text names Darwin."""
    sides = [(None, (ROOT / path).read_text(errors="replace"))] if edit is None else edit
    for lines, text in sides:
        if text is None:
            continue
        spans = darwin_spans(text) if path.endswith(".py") else None
        if spans is None:
            if DARWIN.search(text):
                return True
        elif any(lines is None or any(a <= one <= b for one in lines) for a, b in spans):
            return True
    return False


def edits(base, head, changed):
    """For each changed path, its two sides: the lines the diff touched in `base`'s text and
    that text, then the same of `head`. A side with no file has no text. Where a hunk only adds
    or only drops lines, the lines on each side of where it did count as touched. A path the
    diff shows no hunk header for, such as one git quotes, is left out, so all of it counts."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-renames", base, head],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode:
        raise Unread(f"git diff -U0 failed: {diff.stderr.strip()}")
    touched, seen = {path: (set(), set()) for path in changed}, set()
    path, header = None, False
    for line in diff.stdout.splitlines():
        if line.startswith("diff --git "):
            path, header = None, True
        elif header and line.startswith(("+++ b/", "--- a/")):
            path = line[6:] if line[6:] in touched else path
            seen |= {path} - {None}
        elif hunk := HUNK.match(line):
            header = False
            sides = (hunk.group(1, 2), hunk.group(3, 4))
            for side, (start, count) in zip(touched.get(path, ()), sides, strict=False):
                start, count = int(start), 1 if count is None else int(count)
                side |= set(range(start, start + count)) if count else {start, start + 1}

    def text(commit, path):
        shown = subprocess.run(
            ["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True
        )
        return shown.stdout if shown.returncode == 0 else None

    return {
        path: [(old, text(base, path)), (new, text(head, path))]
        for path, (old, new) in touched.items()
        if path in seen
    }


def within(entries, changed, listed, strict=False, edited=None):
    """The test files of a list's `entries` the changed paths reach on a Mac, sorted, or
    `["all"]`. `listed` is the list's own path. With `strict`, only a changed path of the tests
    or a change to code that branches on Darwin (`branches_on_darwin`, with `edited`'s sides of
    each path) reaches a test, by an import or by its name, and a feature's paths reach none of
    its listed tests: what a pull request's macos job runs, a part of what the run on each merge
    commit runs."""
    if listed in changed:
        return ["all"]
    edited = edited or {}

    @cache
    def follows(path):
        if not strict:
            return on_a_mac(path)
        return (
            of_tests(path)
            or (path in edited or (ROOT / path).is_file())
            and (branches_on_darwin(path, edited.get(path)))
        )

    tests, _ = ruled(changed, follows, cross=False, strict=strict)
    if tests == ["all"]:
        return tests
    return [
        one
        for one in tests
        if any(one == e or e.endswith("/") and one.startswith(e) for e in entries)
    ]


CAUSES = ("imports", "names", "features", "cross-cutting")
# Each cause of a selected file, as the selection's list names it: `added` is a test that
# failed on main.
WHY = {
    "imports": "imports",
    "names": "names",
    "features": "features",
    "cross-cutting": "cross-cutting",
    "models": "models",
    "catch-all": "catch-all",
    "added": "failed-on-main",
}


def total():
    return len([one for one in modules().values() if TEST.fullmatch(one)])


def summary(tests, why, changed):
    chosen = "all" if tests == ["all"] else "some"
    count = total() if chosen == "all" else len(tests)
    counts = {key: len(why.get(key, ())) for key in CAUSES}
    counts["cross-cutting"] = len({*why.get("cross-cutting", ()), *why.get("catch-all", ())})
    causes = " ".join(f"{key}={counts[key]}" for key in CAUSES)
    return (
        f"check-fast selection={chosen} files={count} of={total()} changed={len(changed)} "
        f"{causes} forced-by={why.get('forced-by', '-')}"
    )


def reasons(tests, why, parts=None):
    """The selection's list, a line each: a selected test file and the causes that selected
    it, comma-separated; or first `all` and the path that forced it. With the `parts` it was
    dealt to, each line ends `part=<k>`, `-` for a file that collects no test, or the parts
    that run its tests, comma-separated, for a file dealt by test, and an `all` lists each file
    of the suite after its first line."""
    where = {}
    for at, part in enumerate(parts or [], 1):
        for one in part:
            if not one.startswith("-"):
                where.setdefault(one, []).append(str(at))

    def placed(one):
        return "" if parts is None else f" part={','.join(where.get(one, ['-']))}"

    if tests == ["all"]:
        return [
            f"all forced-by={why['forced-by']}",
            *(f"{one} all{placed(one)}" for one in sorted(where)),
        ]
    by = {key: set(why.get(key, ())) for key in WHY}
    return [
        f"{one} {','.join(WHY[key] for key in WHY if one in by[key])}{placed(one)}" for one in tests
    ]


def listing(lines):
    """The summary's folded block of the selection's list."""
    whole = lines[:1] and lines[0].startswith("all ")
    count = "the whole suite" if whole else f"{len(lines)} test files"
    body = "\n".join(lines)
    return (
        f"<details><summary>selected: {count}, and why</summary>\n\n```\n{body}\n```\n</details>\n"
    )


def unmapped(changed):
    """The changed `.py` files of this tree that are in no module set, so that no import of one
    selects a test, sorted. A path every test rests on, as the root `conftest.py`, selects
    them all."""
    known = set(modules().values()) | set(EVERYTHING)
    return sorted(
        one
        for one in changed
        if one.endswith(".py") and one not in known and (ROOT / one).is_file()
    )


def node_ids(tests):
    """The node ids pytest collects from the selected test files, or from the whole suite for
    `all` (`suite`), with the browser tests left out as `make test` leaves them. Up to
    `COLLECTORS` processes collect at once, each a run of the files or folders, so each file's
    tests come whole from one: the parts deal whole files, and sort them."""
    named = suite() if tests == ["all"] else tests
    count = max(1, min(COLLECTORS, os.cpu_count() or 1, len(named)))
    runs = [named[len(named) * at // count : len(named) * (at + 1) // count] for at in range(count)]

    def collect(share):
        return subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
            + ["-m", "not browser", *share],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    with ThreadPoolExecutor(max_workers=count) as pool:
        ran = list(pool.map(collect, runs))
    for one in ran:
        if one.returncode not in (0, 5):
            sys.exit(
                "select_tests.py: pytest could not collect the selection:\n"
                f"{one.stdout}{one.stderr}"
            )
    return [
        line
        for one in ran
        for line in one.stdout.splitlines()
        if "::" in line and " " not in line.split("::")[0]
    ]


def suite():
    """What pytest collects the whole suite from when it is given no path: each entry of the
    `testpaths` of `pyproject.toml`, a glob from the root, its matches sorted. It is nothing,
    and pytest is given no path, where pytest reads another file's config or finds no match."""
    if not (ROOT / "pyproject.toml").is_file() or any(
        (ROOT / one).exists() for one in ("pytest.ini", ".pytest.ini")
    ):
        return []
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    entries = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths", [])
    return [
        one for entry in entries for one in sorted(glob.glob(entry, root_dir=ROOT, recursive=True))
    ]


def dealt(nodeids, times, count):
    """The words of each of `count` parts, which the part hands `make test TESTS=`, and each part's
    seconds. The test files are dealt by `testing/shard.py`'s split, by the summed seconds of each
    file's tests in `times` (its table) and the seconds of each file's slowest test, which no part
    ends before. A file whose tests sum past a part's share, the selection's seconds over `count`,
    would make its part the last to end whole, so it is cut by test into the fewest pieces that
    each fit a share, split as evenly by seconds, and the pieces are dealt with the files. Fewest,
    since a test file can build a cache once a worker, as the selector's tests build its import
    graph, and each part a piece lands in builds it again. A part that holds a piece gets the file
    and, after its files, the word `--shard-tests=<key>,...`, which names its tests by
    `shard.key`. No tests at all fails."""
    from testing import shard

    if not nodeids:
        sys.exit("select_tests.py: the selection holds no test")
    took, slowest, tests = {}, {}, {}
    for nodeid in nodeids:
        file = nodeid.partition("::")[0]
        took[file] = took.get(file, 0.0) + shard.seconds(times, nodeid)
        slowest[file] = max(slowest.get(file, 0.0), shard.seconds(times, nodeid))
        tests.setdefault(file, []).append(nodeid)
    share = sum(took.values()) / count
    items, pieces = {}, {}
    for file, seconds in took.items():
        cut = min(len(tests[file]), math.ceil(seconds / share))
        if cut < 2:
            items[file] = seconds
            continue
        for at, piece in enumerate(shard.split(tests[file], times, cut), 1):
            name = f"{file}::{at}"
            pieces[name] = piece
            items[name] = sum(shard.seconds(times, nodeid) for nodeid in piece)
            slowest[name] = max(shard.seconds(times, nodeid) for nodeid in piece)
    parts = shard.split(
        list(items), {shard.key(item): seconds for item, seconds in items.items()}, count, slowest
    )
    words = []
    for part in parts:
        keys = sorted(shard.key(nodeid) for item in part for nodeid in pieces.get(item, ()))
        words.append(
            sorted({item.partition("::")[0] for item in part})
            + ([f"--shard-tests={','.join(keys)}"] if keys else [])
        )
    return words, [sum(items[item] for item in part) for part in parts]


def handed(tests, count):
    """Hand the selection to `count` parts: print each part's words, one part a line, give the
    step the output `part<k>` of each and the summary its line, and return the parts."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from testing import shard

    nodeids = node_ids(tests)
    parts, seconds = dealt(nodeids, shard.read_times(shard.TIMES), count)
    for at, part in enumerate(parts, 1):
        print(f"part {at}: {' '.join(part) or 'none'}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as file:
            for at, part in enumerate(parts, 1):
                file.write(f"part{at}={' '.join(part) or 'none'}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as file:
            each = " ".join(f"{one:.0f}" for one in sorted(seconds))
            files = {word for part in parts for word in part if not word.startswith("-")}
            file.write(
                f"parts: {count} of {len(nodeids)} tests in {len(files)} files,"
                f" {each} s of test time each\n\n"
            )
    return parts


def main(argv):
    if argv[:1] == ["--failed-on-main"] and len(argv) == 3:
        print("\n".join(failed_on_main(int(argv[1]), Path(argv[2]))))
        return
    listed = count = cut = None
    strict = argv[2:3] == ["--strict"] and argv[:1] == ["--within"] and len(argv) == 5
    if strict:
        argv = argv[:2] + argv[3:]
    if argv[:1] == ["--within"] and len(argv) == 4:
        listed, argv = argv[1], argv[2:]
    elif argv[:1] == ["--parts"] and len(argv) == 4 and argv[1].isdigit() and int(argv[1]) > 0:
        count, argv = int(argv[1]), argv[2:]
    elif argv[:1] == ["--part"] and len(argv) == 4 and argv[1] in DESK_PARTS:
        cut, argv = argv[1], argv[2:]
    if len(argv) != 2:
        sys.exit(
            "usage: select_tests.py [--within <list> [--strict] | --parts <n>] <base> <head>\n"
            "       select_tests.py --part guards|rest|touched <base> <head>\n"
            "       select_tests.py --failed-on-main <days> <kept>"
        )
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode:
        sys.exit(f"select_tests.py: git diff failed: {diff.stderr.strip()}")
    changed = diff.stdout.splitlines()
    if listed is not None:
        entries = (ROOT / listed).read_text().split()
        try:
            tests = within(
                entries, changed, listed, strict, edits(*argv, changed) if strict else None
            )
        except Unread as error:
            print(f"select_tests.py: nothing can be read ({error}), so all", file=sys.stderr)
            tests = ["all"]
        print("\n".join(tests))
        return
    if cut == "touched":
        print("\n".join(touched(changed)))
        return
    failed = os.environ.get(FAILED_ON_MAIN)
    failed = None if failed is None else failed.split()
    try:
        tests, why = selection(changed, failed or ())
    except Unread as error:
        print(f"select_tests.py: nothing can be read ({error}), so all", file=sys.stderr)
        tests, why = ["all"], {"forced-by": "unread"}
    if cut is not None:
        print("\n".join(desk_part(cut, changed, tests)))
        return
    print("\n".join(tests))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as file:
            file.write(summary(tests, why, changed) + "\n")
            if failed is not None:
                file.write(told(tests, why, failed) + "\n")
            for one in unmapped(changed):
                file.write(
                    f"warning: {one} is in no module set, so no import of it selects a test\n"
                )
            file.write("\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as file:
            chosen = "all" if tests == ["all"] else "some"
            file.write(f"selection={chosen}\n")
            file.write(f"files={'all' if chosen == 'all' else len(tests)}\n")
            file.write(f"forced_by={why.get('forced-by', '')}\n")
    lines = reasons(tests, why)
    try:
        if count is not None:
            lines = reasons(tests, why, handed(tests, count))
    finally:
        # The list is kept and shown also where `handed` fails the step: that run needs it most.
        if os.environ.get("GITHUB_OUTPUT") and os.environ.get("SELECTED"):
            Path(os.environ["SELECTED"]).write_text("\n".join(lines) + "\n")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as file:
                file.write(listing(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
