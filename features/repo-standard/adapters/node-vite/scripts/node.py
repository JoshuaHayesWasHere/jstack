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

Given `--e2e <json>`, the stack's `e2e:` part, it also prints the Playwright tests the change
reaches, as `node_browser` reads them, each in Playwright's test-list form, or `all` when the
change forces every browser test.

`python3 scripts/node.py list --roots <folder> [--roots <folder>]...` prints every unit test of the
roots, one a line from the repo's root, sorted: the whole suite, which
`make test SHARD=<part>/<parts>` deals out to the parts. A Playwright test is no unit test, and
the browser job runs it.

`python3 scripts/node.py e2e --root <folder> --script <name> [--list <file>]` runs the root's npm
script, which runs Playwright, with `--fail-on-flaky-tests`, so a test that passes only on a retry
fails. Given a list, the ids `select` printed, one a line, it passes them on as `--test-list`, each
spec's path made relative to the `testDir` of the config the script runs.

`python3 scripts/node.py test --roots <folder> [--roots <folder>]... [ids]` runs each root's own
`npm test`, from the repo's root as `npm --prefix` runs it: with no id every root's, and given ids,
each a path from the repo's root, `npm test -- <files>` in each root they reach, each file a path
from the root, and nothing in a root they miss. Given `REPO_STANDARD_FAILED=<file>`, it hands
Vitest its JSON reporter beside the default one and appends to the file each test file the report
says failed, one a line, as `list` prints it. A run that fails and names no file, such as one whose
setup throws, appends every file it ran.

`python3 scripts/node.py setup` prints, for `$GITHUB_OUTPUT`, `roots=` and each folder that holds a
`package-lock.json` git tracks, and `version-file=` and the first such root's `.nvmrc`, or its
`package.json` when that sets `engines.node`, or nothing.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

import node_browser
import node_graph
import node_table
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


def hunks(base: str, path: str) -> node_table.Hunks | None:
    """The hunks of a file's change from `base`, or None when the file is new."""
    if not git("ls-tree", "-z", "--name-only", base, "--", path):
        return None
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-color", "--no-ext-diff", base, "--", path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return node_table.hunks_of(diff)


def select(roots: list[str], base: str, e2e: dict | None = None) -> list[str]:
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
    found = {one for one in found if Path(one).is_file()}
    if e2e is not None:
        suite = node_browser.Suite(roots, e2e, files, read)
        browser = suite.select(changed, lambda path: hunks(base, path))
        if browser is None:
            return [ALL]
        found |= {one for one in browser if Path(one.split(" > ")[0]).is_file()}
    return sorted(found)


def e2e(root: str, script: str, listed: str | None) -> int:
    """The exit code of the root's script, run on the listed tests, or on all of them."""
    command = ["npm", "--prefix", root, "run", script, "--", "--fail-on-flaky-tests"]
    if listed is None:
        print(" ".join(command), flush=True)
        return subprocess.run(command).returncode
    files = set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    runner = node_browser.Runner(posixpath.normpath(root), script, files, read)
    ids = [line.strip() for line in read(listed).splitlines() if line.strip()]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as file:
        file.write("".join(f"{one}\n" for one in runner.listed(ids)))
    print(f"{' '.join(command)} --test-list {file.name}", flush=True)
    try:
        return subprocess.run([*command, "--test-list", file.name]).returncode
    finally:
        Path(file.name).unlink()


def listed(roots: list[str]) -> list[str]:
    files = set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *roots))
    tests = [Root(root, files).is_test for root in roots]
    found = [one for one in files if any(is_test(one) for is_test in tests)]
    return sorted(one for one in found if Path(one).is_file())


def failed_in(report: Path) -> list[str]:
    """The test files Vitest's JSON report says failed, from the repo's root."""
    try:
        results = json.loads(report.read_text()).get("testResults") or []
    except (OSError, ValueError, AttributeError):
        return []
    here = Path.cwd()
    return [
        Path(os.path.relpath(one["name"], here)).as_posix()
        for one in results
        if isinstance(one, dict) and one.get("status") == "failed" and one.get("name")
    ]


def test(roots: list[str], ids: list[str]) -> int:
    report = os.environ.get("REPO_STANDARD_FAILED")
    failed = 0
    for root in roots:
        mine = [one for one in ids if within(one, root)]
        if ids and not mine:
            continue
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "vitest.json"
            reporters = ["--reporter=default", "--reporter=json", f"--outputFile.json={out}"]
            rest = [*(reporters if report else []), *(inner(one, root) for one in mine)]
            argv = ["npm", "--prefix", root, "test", *(["--", *rest] if rest else [])]
            print(" ".join(argv), flush=True)
            code = subprocess.run(argv).returncode
            named = failed_in(out)
        failed |= code != 0
        if code and report:
            with open(report, "a", encoding="utf-8") as written:
                written.write("".join(f"{one}\n" for one in named or mine or listed([root])))
    return failed


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


def options(argv: list[str], names: tuple[str, ...]) -> tuple[dict[str, list[str]], list[str]]:
    """Each `--<name> <value>` at the front of the line, and the words after them."""
    found: dict[str, list[str]] = {}
    while len(argv) >= 2 and argv[0].removeprefix("--") in names:
        found.setdefault(argv[0].removeprefix("--"), []).append(argv[1])
        argv = argv[2:]
    return found, argv


def main(argv: list[str]) -> int:
    usage = (
        "usage: node.py select --roots <folder> [--roots <folder>]... [--e2e <json>] <base>"
        " | node.py list --roots <folder> [--roots <folder>]..."
        " | node.py test --roots <folder> [--roots <folder>]... [ids]"
        " | node.py e2e --root <folder> --script <name> [--list <file>] | node.py setup"
    )
    if argv == ["setup"]:
        print("\n".join(setup()))
        return 0
    if argv[:1] == ["e2e"]:
        found, rest = options(argv[1:], ("root", "script", "list"))
        if rest or [len(found.get(one, [])) for one in ("root", "script")] != [1, 1]:
            print(usage, file=sys.stderr)
            return 2
        return e2e(found["root"][0], found["script"][0], (found.get("list") or [None])[-1])
    if not argv or argv[0] not in ("select", "list", "test"):
        print(usage, file=sys.stderr)
        return 2
    verb = argv[0]
    found, rest = options(argv[1:], ("roots", "e2e") if verb == "select" else ("roots",))
    roots = [posixpath.normpath(one) for one in found.get("roots", [])]
    if (
        not roots
        or len(found.get("e2e", [])) > 1
        or (verb != "test" and len(rest) != (1 if verb == "select" else 0))
    ):
        print(usage, file=sys.stderr)
        return 2
    try:
        part = json.loads(found["e2e"][0]) if "e2e" in found else None
    except ValueError:
        print(usage, file=sys.stderr)
        return 2
    try:
        if verb == "test":
            return test(roots, [posixpath.normpath(one) for one in rest])
        selection = select(roots, rest[0], part) if verb == "select" else listed(roots)
    except subprocess.CalledProcessError as error:
        print(f"node.py: git cannot read the tree: {error.stderr.strip()}", file=sys.stderr)
        return 2
    for line in selection:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
