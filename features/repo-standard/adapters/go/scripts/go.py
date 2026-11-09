"""The Go adapter's commands: lint, test and select, over each Go module, with no go.work.

A module is a folder that holds a `go.mod`, wherever it sits in the tree. A test id is a package's
folder from the repo's root, such as `features/alpha/core`, and the package is one that holds a
`*_test.go` file. `go` skips a folder named `testdata` or `vendor`, or one whose name starts with
`.` or `_`, and so does this script.

- `python3 scripts/go.py lint` runs `gofmt -l` on the `.go` files go sees and `go vet ./...` in
  each module, and fails when gofmt names a file.
- `python3 scripts/go.py test [ids]` runs `go test ./...` in each module, or, given ids, `go test`
  on those packages, a run per module. It runs every module before it fails.
- `python3 scripts/go.py select <base>` prints the test ids the change from `<base>` reaches, one a
  line, or `all`. It reads each path that differs between `<base>` and the working tree, and each
  file git does not track yet, and adds up what each selects:

  - A shared path selects `all`: a root file the targets rest on (`SHARED`), and anything under a
    folder of `SHARED_FOLDERS`.
  - A path that a glob of a feature's `reads` matches selects the feature's packages. `reads`, in
    `feature.json`, names the files outside the stack's sight that the feature's tests read.
  - A path inside a module selects the module's packages and those of each module that takes it
    by a `replace` onto a local folder, which is how a module reaches another with no go.work.
  - Outside a module, a Markdown page, a feature's `docs/` and its `feature.json` select nothing.
  - Any other path selects `all`.

  It selects whole modules and leaves the rest to go test's cache, which runs again only a package
  whose inputs changed. It runs in python3 alone, so CI's plan selects before any setup.

Given `--roots <folder>` once or more, before the other arguments, each command works as a stack
of a repo with `stacks:`: it sees only the modules under those roots, and its select ignores a path
outside them that no `reads` names, since the repo's driver places that one. A path under the roots
that the rules above cannot place still selects `all`, which the driver reads as the whole stack.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

SHARED = {"Makefile", ".repo-standard.yml"}
SHARED_FOLDERS = ("scripts/", ".github/", "schemas/")
ALL = "all"
FEATURES = "features"
LOCAL = re.compile(r"^\.{1,2}(?:/|$)")


def skipped(name: str) -> bool:
    return name in ("testdata", "vendor") or name.startswith((".", "_"))


def seen_by_go(path: str) -> bool:
    return not any(skipped(name) for name in PurePosixPath(path).parts)


def folder(path: str) -> str:
    return posixpath.dirname(path) or "."


def within(path: str, module: str) -> bool:
    return module == "." or path == module or path.startswith(f"{module}/")


def replaced(text: str) -> list[str]:
    """The local folders a go.mod's `replace` directives point to, in either form of the block."""
    found, block = [], False
    for line in text.splitlines():
        line = line.split("//")[0].strip()
        if block and line == ")":
            block = False
            continue
        if line.startswith("replace"):
            rest = line[len("replace") :].strip()
            if rest == "(":
                block = True
                continue
            line = rest
        elif not block:
            continue
        if "=>" in line:
            target = line.split("=>", 1)[1].split()
            if target and LOCAL.match(target[0]):
                found.append(target[0])
    return found


def under(path: str, roots: list[str] | None) -> bool:
    return roots is None or any(within(path, root) for root in roots)


class Layout:
    """The repo's modules, each one's test packages, who takes each by `replace`, and the
    features' `reads`, from the files git lists. Given roots, only the modules under them."""

    def __init__(self, paths: list[str], roots: list[str] | None = None) -> None:
        self.roots = roots
        self.modules = sorted(
            {
                folder(p)
                for p in paths
                if PurePosixPath(p).name == "go.mod" and seen_by_go(p) and under(p, roots)
            },
            key=len,
            reverse=True,
        )
        self.packages: dict[str, set[str]] = defaultdict(set)
        self.sources: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            if path.endswith(".go") and seen_by_go(path):
                module = self.module_of(path)
                if module is None:
                    continue
                self.sources[module].append(path)
                if path.endswith("_test.go"):
                    self.packages[module].add(folder(path))
        self.takers: dict[str, set[str]] = defaultdict(set)
        for module in self.modules:
            text = Path(module, "go.mod").read_text(encoding="utf-8", errors="replace")
            for target in replaced(text):
                self.takers[posixpath.normpath(posixpath.join(module, target))].add(module)
        self.reads: dict[str, list[str]] = {}
        for path in paths:
            parts = PurePosixPath(path).parts
            if len(parts) == 3 and parts[0] == FEATURES and parts[2] == "feature.json":
                reads = json.loads(Path(path).read_text(encoding="utf-8")).get("reads", [])
                self.reads[parts[1]] = [one for one in reads if isinstance(one, str)]

    def module_of(self, path: str) -> str | None:
        return next((module for module in self.modules if within(path, module)), None)

    def of_feature(self, name: str) -> set[str]:
        top = f"{FEATURES}/{name}"
        return {one for found in self.packages.values() for one in found if within(one, top)}

    def reach(self, modules: set[str]) -> set[str]:
        """The test packages of these modules and of each module that takes one of them."""
        seen, todo = set(modules), list(modules)
        while todo:
            for taker in self.takers.get(todo.pop(), ()):
                if taker not in seen:
                    seen.add(taker)
                    todo.append(taker)
        return {one for module in seen for one in self.packages.get(module, ())}


def select(paths: list[str], layout: Layout) -> list[str]:
    found: set[str] = set()
    modules: set[str] = set()
    for path in paths:
        if path in SHARED or path.startswith(SHARED_FOLDERS):
            return [ALL]
        placed = False
        for name, globs in layout.reads.items():
            if any(fnmatch.fnmatchcase(path, glob) for glob in globs):
                found |= layout.of_feature(name)
                placed = True
        module = layout.module_of(path)
        if module is not None:
            modules.add(module)
            continue
        if placed or not under(path, layout.roots):
            continue
        parts = PurePosixPath(path).parts
        in_feature = len(parts) >= 3 and parts[0] == FEATURES
        if path.endswith(".md") or (in_feature and parts[2] in ("docs", "feature.json")):
            continue
        return [ALL]
    found |= layout.reach(modules)
    return sorted(one for one in found if Path(one).is_dir())


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [one for one in out.split("\0") if one]


def files() -> list[str]:
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted(one for one in set(listed) if Path(one).is_file())


def run(command: list[str], where: str) -> int:
    print(f"{where}: {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=where).returncode


def lint(layout: Layout) -> int:
    failed = 0
    for module in sorted(layout.modules):
        sources = layout.sources.get(module, [])
        unformatted = subprocess.run(["gofmt", "-l", *sources], capture_output=True, text=True)
        if sources and (unformatted.returncode or unformatted.stdout.strip()):
            print(f"{module}: gofmt -l names files to format:")
            print(f"{unformatted.stdout}{unformatted.stderr}".rstrip())
            failed = 1
        failed |= run(["go", "vet", "./..."], module) != 0
    return failed


def test(layout: Layout, ids: list[str]) -> int:
    runs: dict[str, list[str]] = {module: ["./..."] for module in layout.modules} if not ids else {}
    for one in ids:
        one = posixpath.normpath(one)
        module = layout.module_of(one)
        if module is None:
            print(f"go.py: {one} is in no Go module", file=sys.stderr)
            return 2
        inner = one if module == "." else one[len(module) + 1 :]
        runs.setdefault(module, []).append(f"./{inner}" if inner else ".")
    failed = 0
    for module in sorted(runs):
        failed |= run(["go", "test", *runs[module]], module) != 0
    return failed


def split_roots(argv: list[str]) -> tuple[list[str] | None, list[str]]:
    """The `--roots <folder>` pairs that open the arguments, and the rest."""
    roots = []
    while len(argv) > 2 and argv[1] == "--roots":
        roots.append(posixpath.normpath(argv[2]))
        argv = [argv[0], *argv[3:]]
    return roots or None, argv


def main(argv: list[str]) -> int:
    usage = (
        "usage: go.py lint | go.py test [ids] | go.py select <base>, each verb then [--roots R]..."
    )
    roots, argv = split_roots(argv)
    if not argv or argv[0] not in ("lint", "test", "select"):
        print(usage, file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    try:
        if command == "select":
            if len(rest) != 1:
                print(usage, file=sys.stderr)
                return 2
            changed = git("diff", "-z", "--name-only", "--no-renames", rest[0], "--")
            changed += git("ls-files", "-z", "--others", "--exclude-standard")
            for line in select(sorted(set(changed)), Layout(files(), roots)):
                print(line)
            return 0
        layout = Layout(files(), roots)
    except subprocess.CalledProcessError as error:
        print(f"go.py: git cannot read the tree: {error.stderr.strip()}", file=sys.stderr)
        return 2
    if not layout.modules:
        print("go.py: the repo has no Go module")
        return 0
    try:
        return lint(layout) if command == "lint" else test(layout, rest)
    except FileNotFoundError as error:
        print(f"go.py: {error.filename} is not installed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
