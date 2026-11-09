"""`python3 -m repo_standard stacks lint|test|select|e2e`: the targets of a repo of several stacks.

A repo whose `.repo-standard.yml` sets `stacks:` holds one stack a name, each an adapter over its
own roots (`repo_standard.config.Stack`). The skeleton's Makefile hands `lint`, `test` and
`select` to this driver, which runs each stack's commands (`repo_standard.adapters`) from the
repo's root and joins what they do.

- `lint` runs every stack's lint, then the contract of each stack whose `e2e:` sets `mock:`, a
  shell command run from the repo's root with this standard's `src` on `PYTHONPATH`, so that
  `python3 -m repo_standard routes` is the version the config pins. It fails when any failed.
- `test` with no id runs every stack's whole suite. Given ids, it runs each path id in the stack
  whose root holds it, and an id `stack:<name>` as that stack's whole suite. `test --shard K/N`
  runs part K of N of the whole suite: the ids each stack lists, stack by stack in the config's
  order, dealt to the parts in turn as `repo_standard.plan.deal` deals a selection. A part dealt
  no id runs nothing.
- `select <base>` prints the ids the change from `<base>` reaches, one a line, or `all`. A shared
  path (`SHARED`, or anything under `SHARED_FOLDERS`) selects `all`, and so does a path outside
  every root, unless it is Markdown, a file in a feature's `docs/` or its `feature.json`. Each
  stack's select places the paths under its roots, and one that prints `all` becomes
  `stack:<name>`: `all` is the whole repo, which `repo_standard.plan` reads it as. A node
  stack with `e2e:` adds its browser ids, each a spec's path in Playwright's test-list form:
  `<spec>` or `<spec> > <title>`.
- `e2e [<file>]` runs the browser tests of each stack with `e2e:`. Given a file of ids, one a
  line, it runs each stack the ids reach: on its own ids, or, for `stack:<name>`, on all of them.
"""

from __future__ import annotations

import os
import posixpath
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from repo_standard.adapters import COMMANDS, Argv
from repo_standard.config import Config, Refused, Stack
from repo_standard.plan import deal, shard

SHARED = {"Makefile", ".repo-standard.yml"}
SHARED_FOLDERS = ("scripts/", ".github/", "schemas/")
ALL = "all"
WHOLE = "stack:"
VERBS = ("lint", "test", "select", "e2e")
TITLE = " > "


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


def run(
    command: Argv, quiet: bool = False, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    """The command, run from the repo's root without the PYTHONPATH that reached this driver,
    or with `path` as its PYTHONPATH."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    if path is not None:
        env["PYTHONPATH"] = path
    if quiet:
        return subprocess.run(command, env=env, capture_output=True, text=True)
    print(" ".join(command), flush=True)
    return subprocess.run(command, env=env, text=True)


def lint(config: Config) -> int:
    failed = 0
    for one in config.stacks.values():
        for command in COMMANDS[one.adapter].lint(one.roots):
            failed |= run(command).returncode != 0
    for one in config.stacks.values():
        if one.e2e is not None and one.e2e.mock is not None:
            contract = ["sh", "-c", one.e2e.mock.contract]
            failed |= run(contract, path=str(Path(__file__).resolve().parents[1])).returncode != 0
    return failed


def listed(config: Config) -> list[str]:
    """Every test id of every stack, in the config's order of stacks."""
    found = []
    for name, one in config.stacks.items():
        done = run(COMMANDS[one.adapter].list(one.roots), quiet=True)
        if done.returncode != 0:
            raise Refused(f"the list of stack {name} failed: {done.stderr.strip()}")
        found += [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return found


def test(config: Config, ids: list[str], part: tuple[int, int] | None = None) -> int:
    if part is not None:
        ids = list(deal(tuple(listed(config)), *part))
        if not ids:
            print(f"part {part[0]}/{part[1]} of the suite is dealt no test")
            return 0
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
        done = run(COMMANDS[one.adapter].select(one.roots, base, one.e2e), quiet=True)
        if done.returncode != 0:
            raise Refused(f"the select of stack {name} failed: {done.stderr.strip()}")
        lines = {line.strip() for line in done.stdout.splitlines() if line.strip()}
        found |= {f"{WHOLE}{name}"} if ALL in lines else lines
    return sorted(found)


def e2e(config: Config, listed: str | None) -> int:
    browsers = {name: one for name, one in config.stacks.items() if one.e2e is not None}
    if not browsers:
        raise Refused("no stack of the config sets `e2e:`, so there is no browser test to run")
    if listed is None:
        runs: dict[str, list[str]] = {name: [] for name in browsers}
    else:
        try:
            text = Path(listed).read_text(encoding="utf-8")
        except OSError as error:
            raise Refused(f"cannot read {listed}: {error.strerror}") from error
        ids = [line.strip() for line in text.splitlines() if line.strip()]
        spec = {one: posixpath.normpath(one.split(TITLE)[0]) for one in ids}
        runs = route([one if one.startswith(WHOLE) else spec[one] for one in ids], browsers)
        for name, mine in list(runs.items()):
            runs[name] = [one for one in ids if spec[one] in mine] if mine else []
    failed = 0
    for name, mine in runs.items():
        one = browsers[name]
        command = COMMANDS[one.adapter].e2e
        assert command is not None and one.e2e is not None, "the config sets e2e: on node alone"
        if not mine:
            failed |= run(command(one.e2e, None)).returncode != 0
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as file:
            file.write("".join(f"{line}\n" for line in mine))
        try:
            failed |= run(command(one.e2e, file.name)).returncode != 0
        finally:
            Path(file.name).unlink()
    return failed


def main(root: Path, config: Config, argv: list[str]) -> int:
    """The verb's exit code: 2 when the config has no stack or the verb cannot run."""
    usage = (
        "usage: repo-standard stacks lint | test [ids] | test --shard K/N | select <base>"
        " | e2e [<file>]"
    )
    if not config.stacks:
        print("repo_standard stacks: the config sets no `stacks:`", file=sys.stderr)
        return 2
    sharded = argv[:2] == ["test", "--shard"]
    if (
        not argv
        or argv[0] not in VERBS
        or (argv[0] == "select" and len(argv) != 2)
        or (argv[0] == "e2e" and len(argv) > 2)
        or (sharded and len(argv) != 3)
    ):
        print(usage, file=sys.stderr)
        return 2
    os.chdir(root)
    try:
        if argv[0] == "lint":
            return lint(config)
        if sharded:
            return test(config, [], shard(argv[2]))
        if argv[0] == "test":
            return test(config, argv[1:])
        if argv[0] == "e2e":
            return e2e(config, argv[1] if len(argv) == 2 else None)
        print("".join(f"{line}\n" for line in select(config, argv[1])), end="")
        return 0
    except subprocess.CalledProcessError as error:
        print(f"repo_standard stacks: git cannot read the change: {error.stderr}", file=sys.stderr)
    except FileNotFoundError as error:
        print(f"repo_standard stacks: {error.filename} is not installed", file=sys.stderr)
    except Refused as refused:
        print(f"repo_standard stacks: {refused}", file=sys.stderr)
    return 2
