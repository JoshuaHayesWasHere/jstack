"""Print the tests a change reaches, one a line, or `all`: the selection of the python-uv adapter.

`python3 scripts/select.py <base>` reads each path that differs between `<base>` and the working
tree, committed or not, and each file git does not track yet. Each path selects by these rules:

- A shared path selects `all`: a root file the tests rest on (`SHARED`), anything under a folder
  of `SHARED_FOLDERS`, and any path the rules below cannot place.
- A page of Markdown, a feature's `docs/` and its `feature.json` select nothing.
- A test file, `test_*.py` or `*_test.py` under a feature's `tests/`, selects itself.
- A module under a feature's `src/` selects each test that imports it, directly or through other
  modules. Importing `a.b.c` runs the packages `a` and `a.b` too, so it counts as importing them.
- Any other file under a feature's `src/` or `tests/`, such as a `conftest.py`, a helper or data,
  selects the feature's tests and each test that imports one of the feature's modules.

It prints the test files that exist, sorted, or the one word `all`. It reads the tree with `ast`
and git alone, so CI runs it in the runner's python3 before any setup. A test the imports do not
show, such as one that runs a module in a subprocess, is not selected: main's full run after the
merge is the net that catches it.

`python3 scripts/select.py --roots <folder> [--roots <folder>]... <base>` selects for a stack of a
repo with `stacks:`, whose roots are each a uv project of its own. It ignores a path outside the
roots, which the repo's driver places, and holds each root to these rules:

- The root's `pyproject.toml`, `uv.lock` and `conftest.py` select `all`, which the driver reads as
  the whole stack, and so does any path the rules below cannot place, such as a `Dockerfile`.
- A page of Markdown selects nothing, and a test file selects itself.
- Any other `.py` outside a `tests/` folder is a module, named from the root, or from its `src/`
  when it sits there, and selects each test of the root that imports it.
- Any other file under a `tests/` folder, such as a `conftest.py`, a helper or data, selects each
  test of the root.

`python3 scripts/select.py [--roots <folder>]... --list` prints every test file, one a line,
sorted: the whole suite, which `make test SHARD=<part>/<parts>` deals out to the parts. A test file
is a file git lists, `test_*.py` or `*_test.py`, under `features/`, where the skeleton's pytest
collects, or under the roots. A test pytest is set to find by another name is not listed.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

SHARED = {"pyproject.toml", "uv.lock", "conftest.py", "Makefile", ".repo-standard.yml"}
SHARED_FOLDERS = ("scripts/", ".github/", "schemas/")
ROOT_FILES = {"pyproject.toml", "uv.lock", "conftest.py"}
ALL = "all"


def is_test(name: str) -> bool:
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def module_of(path: str) -> str | None:
    """The dotted name of a module under `features/<feature>/src/`, or None for another path."""
    parts = PurePosixPath(path).parts
    if len(parts) < 4 or parts[0] != "features" or parts[2] != "src" or not path.endswith(".py"):
        return None
    names = [*parts[3:-1], PurePosixPath(path).stem]
    if names[-1] == "__init__":
        names.pop()
    return ".".join(names) or None


def imported(path: Path, module: str | None) -> set[str]:
    """Each module name a file imports, with every package above it."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    package = module.split(".") if module else []
    if module and path.name != "__init__.py":
        package = package[:-1]
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            above = package[: len(package) - node.level + 1] if node.level else []
            base = ".".join([*above, *([node.module] if node.module else [])])
            if base:
                names.add(base)
            names.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return {
        ".".join(name.split(".")[:end]) for name in names for end in range(1, name.count(".") + 2)
    }


def within(path: str, root: str) -> bool:
    return root == "." or path == root or path.startswith(f"{root}/")


def rooted_module(inner: PurePosixPath) -> str | None:
    """The dotted name of a module at `inner` in a root, or None for a test or a file of tests/."""
    if inner.suffix != ".py" or is_test(inner.name) or "tests" in inner.parts[:-1]:
        return None
    names = [*inner.parts[:-1], inner.stem]
    if names[0] == "src":
        names.pop(0)
    if names and names[-1] == "__init__":
        names.pop()
    return ".".join(names) or None


class Tree:
    """The modules and tests of each feature, or of each root, and who imports each module."""

    def __init__(self, files: dict[str, tuple[str, str | None]]) -> None:
        """`files` maps each module and test file to its feature or root, and its module name,
        which is None for a test."""
        self.modules: dict[str, set[str]] = defaultdict(set)
        self.tests: dict[str, set[str]] = defaultdict(set)
        self.importers: dict[str, set[str]] = defaultdict(set)
        self.module: dict[str, str | None] = {}
        for relative, (unit, module) in sorted(files.items()):
            if module:
                self.modules[unit].add(module)
            else:
                self.tests[unit].add(relative)
            self.module[relative] = module
            for name in imported(Path(relative), module):
                self.importers[name].add(relative)

    @classmethod
    def of_features(cls, root: Path) -> Tree:
        files: dict[str, tuple[str, str | None]] = {}
        for path in root.glob("features/*/*/**/*.py"):
            relative = path.relative_to(root).as_posix()
            feature, part = PurePosixPath(relative).parts[1:3]
            module = module_of(relative)
            if module or (part == "tests" and is_test(path.name)):
                files[relative] = (feature, module)
        return cls(files)

    @classmethod
    def of_root(cls, root: str, paths: list[str]) -> Tree:
        files: dict[str, tuple[str, str | None]] = {}
        for path in paths:
            inner = PurePosixPath(path).relative_to(root) if root != "." else PurePosixPath(path)
            module = rooted_module(inner)
            if module or (inner.suffix == ".py" and is_test(inner.name)):
                files[path] = (root, module)
        return cls(files)

    def reach(self, modules: set[str]) -> set[str]:
        """The tests that import any of these modules, directly or through other modules."""
        seen, todo, found = set(modules), list(modules), set()
        while todo:
            for path in self.importers.get(todo.pop(), ()):
                module = self.module[path]
                if module is None:
                    found.add(path)
                elif module not in seen:
                    seen.add(module)
                    todo.append(module)
        return found


def select(paths: list[str], tree: Tree) -> list[str]:
    modules: set[str] = set()
    found: set[str] = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        if path in SHARED or path.startswith(SHARED_FOLDERS):
            return [ALL]
        if path.endswith(".md"):
            continue
        if parts[0] != "features" or len(parts) < 3:
            return [ALL]
        feature, part = parts[1], parts[2]
        if part == "docs" or (part == "feature.json" and len(parts) == 3):
            continue
        if part not in ("src", "tests"):
            return [ALL]
        module = module_of(path)
        if module:
            modules.add(module)
        elif part == "tests" and is_test(parts[-1]):
            found.add(path)
        else:
            found |= tree.tests[feature]
            modules |= tree.modules[feature]
    found |= tree.reach(modules)
    return sorted(path for path in found if Path(path).is_file())


def select_rooted(paths: list[str], trees: dict[str, Tree]) -> list[str]:
    """The selection of a stack whose roots are the keys of `trees`, one tree a root."""
    found: set[str] = set()
    for root, tree in trees.items():
        modules: set[str] = set()
        for path in paths:
            if not within(path, root):
                continue
            inner = PurePosixPath(path).relative_to(root) if root != "." else PurePosixPath(path)
            if str(inner) in ROOT_FILES:
                return [ALL]
            if inner.suffix == ".md":
                continue
            module = rooted_module(inner)
            if module:
                modules.add(module)
            elif inner.suffix == ".py" and is_test(inner.name):
                found.add(path)
            elif "tests" in inner.parts[:-1]:
                found |= tree.tests[root]
            else:
                return [ALL]
        found |= tree.reach(modules)
    return sorted(path for path in found if Path(path).is_file())


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [one for one in out.split("\0") if one]


def main(argv: list[str]) -> int:
    roots = []
    while len(argv) > 2 and argv[0] == "--roots":
        roots.append(str(PurePosixPath(argv[1])))
        argv = argv[2:]
    if len(argv) != 1:
        print("usage: select.py [--roots <folder>]... <base> | --list", file=sys.stderr)
        return 2
    try:
        if argv == ["--list"]:
            scope = roots or ["features"]
            listed = git("ls-files", "-z", "-co", "--exclude-standard", "--", *scope)
            for line in sorted({one for one in listed if is_test(PurePosixPath(one).name)}):
                if Path(line).is_file():
                    print(line)
            return 0
        changed = git("diff", "-z", "--name-only", "--no-renames", argv[0], "--")
        changed += git("ls-files", "-z", "--others", "--exclude-standard")
    except subprocess.CalledProcessError as error:
        print(
            f"select.py: git cannot read the change from {argv[0]}: {error.stderr.strip()}",
            file=sys.stderr,
        )
        return 2
    changed = sorted(set(changed))
    if roots:
        listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *roots)
        trees = {
            root: Tree.of_root(root, [one for one in listed if within(one, root)]) for root in roots
        }
        selection = select_rooted(changed, trees)
    else:
        selection = select(changed, Tree.of_features(Path(".")))
    for line in selection:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
