"""A doc or a docstring that names a module, a symbol or a path of this tree names one that exists.

The class has been upheld twice: #933's `stall.py` sent the reader to `jbus.telemetry.schema`'s
`weekly_stall` after a rebase had moved that view to `jbus.telemetry.views`, and #961's brief
named a `features/jbus/src/jbus/telemetry/files.py` that no commit made. Each was a review
finding. The test makes it a red check instead.

It reads two kinds of names, each in backticks:

- a dotted name that starts with a package of a feature's `src/`, as `jbus.telemetry.views` or
  `jbus.stall.twice`, and the form `` `<module>`'s `<name>` ``. The longest leading part that is a
  module or a package of the tree is the module, and each part after it must be bound there: at
  the module's top level (a `def`, a `class`, an assignment or an import), as a submodule, or in
  the body of the class the part before it names. A name that stops at a package's top, as
  `jbus.steer`, is not read, since jbus names its message sources and records that way too.
- a path that starts at `features/` or `testing/`, in a Python file of a feature's `src/` or
  `scripts/`, of `scripts/` or of `testing/`. It must exist. `check-jstack-docs.py` checks the
  paths of the Markdown pages, and the tests name paths of their fixtures, so the test reads
  neither. A path that holds a `<placeholder>` or a glob is not read.

It reads every Python file of those folders and of the tests, and every Markdown file of the
features and of `docs/`, with the README, except a test's fixtures and the recorded eval runs.
"""

import ast
import re
from functools import cache
from pathlib import Path

from testing.paths import REPO, sources

READ_SET = (
    "*.py",
    "*.md",
)

PACKAGES = {
    package.parent.name: package.parent
    for root in sources()
    for package in sorted(root.glob("*/__init__.py"))
}
TREE_PATH = re.compile(r"`((?:features|testing)/[\w.-]+(?:/[\w.-]+)*)`")
PATH_READ = (
    "features/*/src/**/*.py",
    "features/*/scripts/**/*.py",
    "scripts/**/*.py",
    "testing/*.py",
)
READ = (
    *PATH_READ,
    "features/*/tests/**/*.py",
    "testing/tests/**/*.py",
    "features/**/*.md",
    "docs/**/*.md",
    "README.md",
)
SKIPPED = ("fixtures", "evals/evals")


def module_of(parts: list[str], packages: dict[str, Path]) -> tuple[Path | None, list[str]]:
    """The file of the longest leading part of `parts` that is a module or a package, with the
    parts after it."""
    for end in range(len(parts), 0, -1):
        place = packages[parts[0]].joinpath(*parts[1:end])
        for file in (place.with_suffix(".py"), place / "__init__.py"):
            if file.is_file():
                return file, parts[end:]
    return None, parts


def bound(body: list[ast.stmt]) -> dict[str, ast.AST | None]:
    """The names a module or a class body binds, each with its class or its `def`, if it is one."""
    found: dict[str, ast.AST | None] = {}
    for node in (one for statement in body for one in ast.walk(statement)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.setdefault(node.name, node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.setdefault(node.id, None)
        elif isinstance(node, ast.alias):
            found.setdefault((node.asname or node.name).split(".")[0], None)
    return found


@cache
def top(file: Path) -> dict[str, ast.AST | None]:
    """What a module binds, at any depth of its own statements, so a name bound under an `if` or a
    `try` counts. A name bound inside a function counts too: the test would rather miss a stale
    name than call a real one stale."""
    return bound(ast.parse(file.read_text()).body)


def unresolved(dotted: str, after: str | None, packages: dict[str, Path] = PACKAGES) -> str | None:
    """Why `dotted`, with the name its `'s` form gives after it, names nothing, or None."""
    parts = dotted.split(".")
    file, rest = module_of(parts, packages)
    if file is None or file == packages[parts[0]] / "__init__.py":
        return None
    owner = ".".join(parts[: len(parts) - len(rest)])
    names = top(file)
    for part in [*rest, after] if after else rest:
        if part not in names and not (file.parent / part).is_dir():
            return f"`{owner}` has no `{part}`"
        node = names.get(part)
        names = bound(node.body) if isinstance(node, ast.ClassDef) else {}
        owner = f"{owner}.{part}"
        if not names:
            return None
    return None


def files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    found = {path for pattern in patterns for path in root.glob(pattern)}
    return sorted(
        path
        for path in found
        if not any(skip in path.relative_to(root).as_posix() for skip in SKIPPED)
    )


def problems(root: Path = REPO, packages: dict[str, Path] = PACKAGES) -> list[str]:
    """Each name of the tree a doc or a docstring gives that names nothing, as
    `<file>:<line> <why>`."""
    pathed = set(files(root, PATH_READ))
    name = rf"`((?:{'|'.join(packages)})(?:\.\w+)+)(?:\(\))?`"
    dotted = re.compile(rf"{name}(?:'s `(\w+)(?:\(\))?`)?")
    found = []
    for file in files(root, READ):
        where = file.relative_to(root).as_posix()
        for number, line in enumerate(file.read_text().splitlines(), 1):
            spans = [
                (span[0], unresolved(span[1], span[2], packages)) for span in dotted.finditer(line)
            ]
            found += [f"{where}:{number} names {span}, but {why}" for span, why in spans if why]
            paths = (
                [path.rstrip(".,:;") for path in TREE_PATH.findall(line)] if file in pathed else []
            )
            found += [
                f"{where}:{number} names `{path}`, and the tree has no such path"
                for path in paths
                if "<" not in path and "*" not in path and not (root / path).exists()
            ]
    return found


def test_every_module_symbol_and_path_a_doc_names_is_in_the_tree():
    assert problems() == [], "\n".join(
        ["name what is there now: move the pointer to the module that holds it", *problems()]
    )


def test_a_moved_symbol_and_a_missing_path_each_fail_and_what_is_there_passes(tmp_path):
    package = tmp_path / "features/pkg/src/pkg"
    (package / "telemetry/views").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "telemetry/__init__.py").write_text("")
    (package / "telemetry/schema.py").write_text("TABLES = ()\n")
    (package / "telemetry/views/weekly_stall.py").write_text("SQL = ''\n")
    (package / "stall.py").write_text(
        "class Pass:\n"
        "    def twice(self):\n"
        "        pass\n"
        '"""Read by `pkg.telemetry.schema`\'s `weekly_stall`,\n'
        "now `pkg.telemetry.views.weekly_stall`.\n"
        "`pkg.stall.Pass.twice` runs, `pkg.stall.Pass.thrice` does not, `pkg.steer` is a source.\n"
        "The readers live in `features/pkg/src/pkg/telemetry/files.py`,\n"
        "beside `features/pkg/src/pkg/stall.py`.\n"
        '"""\n'
    )
    found = problems(tmp_path, {"pkg": package})
    assert found == [
        "features/pkg/src/pkg/stall.py:4 names `pkg.telemetry.schema`'s `weekly_stall`, "
        "but `pkg.telemetry.schema` has no `weekly_stall`",
        "features/pkg/src/pkg/stall.py:6 names `pkg.stall.Pass.thrice`, "
        "but `pkg.stall.Pass` has no `thrice`",
        "features/pkg/src/pkg/stall.py:7 names `features/pkg/src/pkg/telemetry/files.py`, "
        "and the tree has no such path",
    ]
