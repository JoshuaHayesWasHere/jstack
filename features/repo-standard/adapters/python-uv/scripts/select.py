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
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

SHARED = {"pyproject.toml", "uv.lock", "conftest.py", "Makefile", ".repo-standard.yml"}
SHARED_FOLDERS = ("scripts/", ".github/", "schemas/")
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


class Tree:
    """The features' modules and tests, and who imports each module."""

    def __init__(self, root: Path) -> None:
        self.modules: dict[str, set[str]] = defaultdict(set)
        self.tests: dict[str, set[str]] = defaultdict(set)
        self.importers: dict[str, set[str]] = defaultdict(set)
        for path in sorted(root.glob("features/*/*/**/*.py")):
            relative = path.relative_to(root).as_posix()
            feature, part = PurePosixPath(relative).parts[1:3]
            module = module_of(relative)
            if module:
                self.modules[feature].add(module)
            elif part == "tests" and is_test(path.name):
                self.tests[feature].add(relative)
            else:
                continue
            for name in imported(path, module):
                self.importers[name].add(relative)

    def reach(self, modules: set[str]) -> set[str]:
        """The tests that import any of these modules, directly or through other modules."""
        seen, todo, found = set(modules), list(modules), set()
        while todo:
            for path in self.importers.get(todo.pop(), ()):
                module = module_of(path)
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


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [one for one in out.split("\0") if one]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: select.py <base>", file=sys.stderr)
        return 2
    try:
        changed = git("diff", "-z", "--name-only", "--no-renames", argv[0], "--")
        changed += git("ls-files", "-z", "--others", "--exclude-standard")
    except subprocess.CalledProcessError as error:
        print(
            f"select.py: git cannot read the change from {argv[0]}: {error.stderr.strip()}",
            file=sys.stderr,
        )
        return 2
    for line in select(sorted(set(changed)), Tree(Path("."))):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
