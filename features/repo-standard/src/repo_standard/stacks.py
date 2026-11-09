"""`python3 -m repo_standard stacks lint|test|select`: the targets of a repo of several stacks.

A repo whose `.repo-standard.yml` sets `stacks:` holds one stack a name, each an adapter over its
own roots (`repo_standard.config.Stack`). The skeleton's Makefile hands `lint`, `test` and
`select` to this driver, which runs each stack's commands (`repo_standard.adapters`) from the
repo's root and joins what they do.

- `lint` runs every stack, and fails when any failed.
- `test` with no id runs every stack's whole suite. Given ids, it runs each path id in the stack
  whose root holds it, and an id `stack:<name>` as that stack's whole suite.
- `select <base>` prints the ids the change from `<base>` reaches, one a line, or `all`. A shared
  path (`SHARED`, or anything under `SHARED_FOLDERS`) selects `all`, and so does a path outside
  every root, unless it is Markdown, a file in a feature's `docs/` or its `feature.json`. Each
  stack's select places the paths under its roots, and one that prints `all` becomes
  `stack:<name>`: `all` is the whole repo, which `repo_standard.plan` reads it as.
"""

from __future__ import annotations

import os
import posixpath
import subprocess
import sys
from pathlib import Path, PurePosixPath

from repo_standard.adapters import COMMANDS, Argv
from repo_standard.config import Config, Refused, Stack

SHARED = {"Makefile", ".repo-standard.yml"}
SHARED_FOLDERS = ("scripts/", ".github/", "schemas/")
ALL = "all"
WHOLE = "stack:"
VERBS = ("lint", "test", "select")


def within(path: str, root: str) -> bool:
    return root == "." or path == root or path.startswith(f"{root}/")


def owner(path: str, stacks: dict[str, Stack]) -> str | None:
    """The stack whose root holds the path: roots never overlap, so there is one at most."""
    return next(
        (name for name, one in stacks.items() if any(within(path, r) for r in one.roots)), None
    )


def route(ids: list[str], stacks: dict[str, Stack]) -> dict[str, list[str]]:
    """Each stack the ids reach, with its ids, or an empty list for its whole suite."""
    runs: dict[str, list[str]] = {}
    whole: set[str] = set()
    for one in ids:
        if one.startswith(WHOLE):
            name = one[len(WHOLE) :]
            if name not in stacks:
                raise Refused(f"{one} names no stack of the config")
            whole.add(name)
            continue
        one = posixpath.normpath(one)
        name = owner(one, stacks)
        if name is None:
            raise Refused(f"{one} is under no stack's roots")
        runs.setdefault(name, []).append(one)
    return {name: [] if name in whole else runs.get(name, []) for name in [*runs, *whole]}


def unplaced(path: str, config: Config) -> bool:
    """Whether a path outside every root selects the whole repo."""
    parts = PurePosixPath(path).parts
    in_feature = len(parts) >= 3 and parts[0] == config.features
    return not (path.endswith(".md") or (in_feature and parts[2] in ("docs", "feature.json")))


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [one for one in out.split("\0") if one]


def run(command: Argv, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    """The command, run from the repo's root without the PYTHONPATH that reached this driver."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    if quiet:
        return subprocess.run(command, env=env, capture_output=True, text=True)
    print(" ".join(command), flush=True)
    return subprocess.run(command, env=env, text=True)


def lint(config: Config) -> int:
    failed = 0
    for one in config.stacks.values():
        for command in COMMANDS[one.adapter].lint(one.roots):
            failed |= run(command).returncode != 0
    return failed


def test(config: Config, ids: list[str]) -> int:
    runs = route(ids, config.stacks) if ids else {name: [] for name in config.stacks}
    failed = 0
    for name, mine in runs.items():
        one = config.stacks[name]
        for command in COMMANDS[one.adapter].test(one.roots, mine):
            failed |= run(command).returncode != 0
    return failed


def select(config: Config, base: str) -> list[str]:
    changed = git("diff", "-z", "--name-only", "--no-renames", base, "--")
    changed += git("ls-files", "-z", "--others", "--exclude-standard")
    for path in changed:
        if path in SHARED or path.startswith(SHARED_FOLDERS):
            return [ALL]
        if owner(path, config.stacks) is None and unplaced(path, config):
            return [ALL]
    found: set[str] = set()
    for name, one in config.stacks.items():
        done = run(COMMANDS[one.adapter].select(one.roots, base), quiet=True)
        if done.returncode != 0:
            raise Refused(f"the select of stack {name} failed: {done.stderr.strip()}")
        lines = {line.strip() for line in done.stdout.splitlines() if line.strip()}
        found |= {f"{WHOLE}{name}"} if ALL in lines else lines
    return sorted(found)


def main(root: Path, config: Config, argv: list[str]) -> int:
    """The verb's exit code: 2 when the config has no stack or the verb cannot run."""
    usage = "usage: repo-standard stacks lint | test [ids] | select <base>"
    if not config.stacks:
        print("repo_standard stacks: the config sets no `stacks:`", file=sys.stderr)
        return 2
    if not argv or argv[0] not in VERBS or (argv[0] == "select" and len(argv) != 2):
        print(usage, file=sys.stderr)
        return 2
    os.chdir(root)
    try:
        if argv[0] == "lint":
            return lint(config)
        if argv[0] == "test":
            return test(config, argv[1:])
        print("".join(f"{line}\n" for line in select(config, argv[1])), end="")
        return 0
    except subprocess.CalledProcessError as error:
        print(f"repo_standard stacks: git cannot read the change: {error.stderr}", file=sys.stderr)
    except FileNotFoundError as error:
        print(f"repo_standard stacks: {error.filename} is not installed", file=sys.stderr)
    except Refused as refused:
        print(f"repo_standard stacks: {refused}", file=sys.stderr)
    return 2
