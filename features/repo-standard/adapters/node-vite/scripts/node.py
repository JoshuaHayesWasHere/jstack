"""The node-vite adapter's selection and setup, in python3 alone, for a stack of npm roots.

A root is a folder that holds an npm package: its `package.json`, whose `check` and `test` scripts
the repo's driver runs, and its `package-lock.json`. A unit test is a file the root's Vitest config
includes: the globs of a literal `include` in the config's `test` block, or, with none, a file
named `*.test.<ext>`, so that a Playwright `*.spec.ts` beside it is no unit test.

`python3 scripts/node.py select --roots <folder> [--roots <folder>]... <base>` prints the unit
tests the change from `<base>` reaches, one a line from the repo's root, or `all`, which the driver
reads as the whole stack. It reads each path that differs between `<base>` and the working tree,
and each file git does not track yet, and holds each root to these rules:

- A file every test rests on selects `all`: `package.json`, the lockfile, `.nvmrc`, `.npmrc`, a
  Vite, Vitest, Svelte, TypeScript, PostCSS or Tailwind config (`FORCING`), wherever it sits in the
  root, each setup file the Vitest config names, each file the package's `test` script names,
  such as a script that starts Vitest, and every file one of those imports.
- A page of Markdown selects nothing.
- A file the import graph places, a source file of the root or a file one of them reaches, selects
  each test that reaches it, as `node_graph` reads the imports. A test reaches itself.
- Any other path under the root, such as a file under `static/` or `index.html`, selects `all`.
- A path outside the roots selects the tests that name it, and nothing else: the driver places it.

A deleted file still has the tests that imported it, since the graph resolves against the files
of the change as well as the tree's. Only the tests that exist print.

`python3 scripts/node.py setup` prints, for `$GITHUB_OUTPUT`, `roots=` and each folder that holds a
`package-lock.json` git tracks, and `version-file=` and the first such root's `.nvmrc`, or its
`package.json` when that sets `engines.node`, or nothing.
"""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import node_graph
from node_graph import Graph, within

ALL = "all"
LOCKFILE = "package-lock.json"
FORCING = node_graph.matcher(
    [
        "package.json",
        LOCKFILE,
        "npm-shrinkwrap.json",
        ".nvmrc",
        ".npmrc",
        "vite.config.*",
        "vitest.config.*",
        "vitest.workspace.*",
        "svelte.config.*",
        "tsconfig*.json",
        "postcss.config.*",
        "tailwind.config.*",
    ]
)
CONFIGS = node_graph.matcher(["vite.config.*", "vitest.config.*"])
TEST_NAME = re.compile(r"\.test\.[cm]?[jt]sx?$")
SETUP = re.compile(r"\b(?:setupFiles|globalSetup)\s*:\s*(\[[^\]]*\]|'[^'\n]*'|\"[^\"\n]*\")")
INCLUDE = re.compile(r"\binclude\s*:\s*(\[[^\]]*\])")
TEST_BLOCK = re.compile(r"\btest\s*:\s*\{")


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [one for one in out.split("\0") if one]


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def inner(path: str, root: str) -> str:
    return path if root == "." else path[len(root) + 1 :]


def test_block(text: str) -> str:
    """The top level of the config's `test: {...}` block, with each block inside it cut out, and
    nothing when it has none. A brace inside a string, such as a glob's `{ts,tsx}`, stays."""
    found = TEST_BLOCK.search(text)
    if not found:
        return ""
    kept, depth, quote = [], 1, ""
    for char in text[found.end() :]:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"`":
            quote = char
        elif char in "{}":
            depth += 1 if char == "{" else -1
            if depth == 0:
                break
            continue
        if depth == 1:
            kept.append(char)
    return "".join(kept)


class Root:
    """One npm root: its Vitest config's includes, its tests, its graph, and the files that force
    the whole stack: the config's setup files, the files the `test` script names, and each file
    they import."""

    def __init__(self, root: str, files: set[str]) -> None:
        self.root = root
        configs = sorted(
            path
            for path in files
            if within(path, root)
            and "/" not in inner(path, root)
            and CONFIGS.fullmatch(inner(path, root))
        )
        setup, include = [], []
        for config in configs:
            text = read(config)
            for found in SETUP.finditer(text):
                setup += [one[2] for one in node_graph.QUOTED.finditer(found[1])]
            listed = INCLUDE.search(test_block(text))
            if listed:
                include += [one[2] for one in node_graph.QUOTED.finditer(listed[1])]
        self.include = node_graph.matcher(include) if include else None
        self.graph: Graph = node_graph.build(root, files, read, self.is_test)
        try:
            scripts = json.loads(read(node_graph.join(root, "package.json"))).get("scripts")
            words = scripts["test"].split() if isinstance(scripts["test"], str) else []
        except (ValueError, AttributeError, KeyError, TypeError):
            words = []
        bases = {node_graph.join(root, one.removeprefix("./")) for one in [*setup, *words]}
        self.forcing = self.graph.closure(
            {found for base in bases for found in [self.graph.resolver.file(base)] if found}
        )

    def is_test(self, path: str) -> bool:
        if not within(path, self.root) or "node_modules" in path.split("/"):
            return False
        if self.include is not None:
            return self.include.fullmatch(inner(path, self.root)) is not None
        return TEST_NAME.search(path) is not None


def select_root(changed: list[str], root: Root) -> set[str] | None:
    """The tests of one root the change reaches, or None for every test of the root."""
    start = set()
    for path in changed:
        if not within(path, root.root):
            if path in root.graph.importers:
                start.add(path)
            continue
        name = inner(path, root.root)
        if FORCING.fullmatch(PurePosixPath(name).name) or path in root.forcing:
            return None
        if name.endswith(".md"):
            continue
        if not (root.graph.holds(path) or root.is_test(path)):
            return None
        start.add(path)
    return {one for one in root.graph.reach(start) if root.is_test(one)}


def select(roots: list[str], base: str) -> list[str]:
    changed = git("diff", "-z", "--name-only", "--no-renames", base, "--")
    changed += git("ls-files", "-z", "--others", "--exclude-standard")
    changed = sorted(set(changed))
    tracked = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    files = set(tracked) | set(changed)
    found: set[str] = set()
    for root in roots:
        mine = select_root(changed, Root(root, files))
        if mine is None:
            return [ALL]
        found |= mine
    return sorted(one for one in found if Path(one).is_file())


def node_version(root: str) -> str:
    """The file setup-node reads the root's Node version from, or nothing."""
    nvmrc = node_graph.join(root, ".nvmrc")
    if Path(nvmrc).is_file():
        return nvmrc
    package = node_graph.join(root, "package.json")
    try:
        engines = json.loads(read(package)).get("engines") or {}
    except (ValueError, AttributeError):
        return ""
    return package if isinstance(engines, dict) and engines.get("node") else ""


def setup() -> list[str]:
    roots = sorted(
        posixpath.dirname(path) or "."
        for path in git("ls-files", "-z", "--", f"*{LOCKFILE}")
        if posixpath.basename(path) == LOCKFILE and "node_modules" not in path.split("/")
    )
    version = next((found for root in roots for found in [node_version(root)] if found), "")
    return [f"roots={' '.join(roots)}", f"version-file={version}"]


def main(argv: list[str]) -> int:
    usage = "usage: node.py select --roots <folder> [--roots <folder>]... <base> | node.py setup"
    if argv == ["setup"]:
        print("\n".join(setup()))
        return 0
    if not argv or argv[0] != "select":
        print(usage, file=sys.stderr)
        return 2
    argv, roots = argv[1:], []
    while len(argv) > 2 and argv[0] == "--roots":
        roots.append(posixpath.normpath(argv[1]))
        argv = argv[2:]
    if len(argv) != 1 or not roots:
        print(usage, file=sys.stderr)
        return 2
    try:
        selection = select(roots, argv[0])
    except subprocess.CalledProcessError as error:
        print(
            f"node.py: git cannot read the change from {argv[0]}: {error.stderr.strip()}",
            file=sys.stderr,
        )
        return 2
    for line in selection:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
