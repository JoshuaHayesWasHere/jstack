"""`repo-standard <verb> [--root DIR] [--config FILE]`: run one guard on a repo, or conform.

`repo-standard` is the command, and `python -m repo_standard` runs the same. The verb `conform`
holds the repo to every rule of the standard (`repo_standard.conform`), prints each fault, waiver
and note, and exits 1 on an error. `--upstream` names the repo whose `repo-standard-vN` tags it
lists for a newer version, and `--list` prints each rule's level and id and checks nothing.

The verb `plan` prints, as `key=value` lines for `$GITHUB_OUTPUT`, what the shared check
workflow's jobs run (`repo_standard.plan`): it reads the config's `check` and `stacks` parts, the
lockfile of each stack's e2e root, the event from `--event` or `$GITHUB_EVENT_NAME`, and a pull
request's selection from `--selection`, the file `make select` wrote.

The verb `stacks` runs the targets `lint`, `test`, `select` and `e2e` of a repo whose config sets
`stacks:`, each stack over its own roots (`repo_standard.stacks`), and takes the rest of the line
as its own: `stacks lint`, `stacks test [ids]`, `stacks test --shard K/N`, `stacks select <base>`
or `stacks e2e [<file>]`.

The verb `upgrade --to N` moves the repo to version N of the standard
(`repo_standard.upgrade`): its pin, its call of the shared check and every file the version owns.
It runs from the tool at version N, and `--upstream` names where it clones that version's files
from when the tool's own tree does not hold them. It prints what it wrote and what it left.

The verb `green` says whether the checkout may deploy (`repo_standard.green`): it exits 0 on a
clean checkout of the remote's main whose tree passed the check, 1 with each reason it may not,
and 2 when it cannot ask the remote or GitHub. It reads no config.

The verb `routes --producer <cmd> --mock <cmd>` is the reference contract of a stack's mock API
(`repo_standard.routes`): it fails on each route the mock answers that the real API lacks. It
reads no config, and a stack's `mock.contract` runs it from the repo's root during `make lint`.

The verb `misses` reads the ledger of the tests main's runs failed (`repo_standard.misses`).
`misses --days N` prints the miss rate of the last N days, rows of class `miss` per merged pull
request, and the rows. The shared check runs the other two: `misses record --failed DIR --out DIR`
writes the ledger of this commit of main from the ids its parts failed, and `misses failing --days
N` prints the ids a pull request's selection adds, and only warns where it cannot ask GitHub.

The verb `floor` prints the python3 it runs in and the standard's floor, `repo_standard.PYTHON`.
`python -m repo_standard` refuses a python3 under that floor before any verb, naming the floor, so
the shared check's plan job and the skeleton's `make lint` run it first.

The guards are `borders`, `stale`, `docs`, `size` and `comments`. Each reads the repo's
`.repo-standard.yml`, prints one line for each fault it finds, and exits 1 on any. `borders`
prints each fault as a warning GitHub reads and exits 0 when it warns, or 1 under `--hard`. Every
guard exits 2 when it cannot read the config, the tree or the base: a guard that cannot look never
passes. It uses the standard library only, so CI runs it before any install.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from repo_standard import (
    PYTHON,
    borders,
    conform,
    docs_true,
    misses,
    plan,
    routes,
    size,
    stacks,
    stale,
    upgrade,
)
from repo_standard.config import Refused, load
from repo_standard.tree import Unreadable, tracked

GUARDS = ("borders", "stale", "docs", "size", "comments")
VERBS = (*GUARDS, "conform", "plan", "stacks", "upgrade", "green", "routes", "misses", "floor")


def _root(given: str | None) -> Path:
    if given:
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        raise Unreadable(f"not in a git checkout: {top.stderr.strip()}")
    return Path(top.stdout.strip())


def _warn(line: str) -> None:
    print(f"::warning::misses: {line}", file=sys.stderr)


def _misses(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="repo-standard misses", description=misses.__doc__)
    parser.add_argument("verb", nargs="?", choices=("record", "failing"), help="none: the rate")
    parser.add_argument("--days", type=int, default=misses.DAYS, help="the window, in days")
    parser.add_argument("--failed", help="record: the folder of the failed ids the parts wrote")
    parser.add_argument("--out", help="record: the folder the ledger is written to")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.verb == "failing":
        try:
            found = misses.failing_here(
                misses.GitHub(misses.repository(env)), misses.workflow(env), args.days
            )
        except Exception as error:
            _warn(f"could not read main's ledgers ({error}), so the selection adds nothing")
            return 0
        print("".join(f"{one}\n" for one in found), end="")
        print(f"misses: {len(found)} tests main failed join the selection", file=sys.stderr)
        return 0
    try:
        github = misses.GitHub(misses.repository(env))
        if args.verb == "record":
            if not (args.failed and args.out):
                parser.error("record needs --failed and --out")
            root = _root(None)
            rows = misses.record_here(
                Path(args.failed), Path(args.out), github, load(root).stacks, _warn
            )
            table = misses.table(rows)
            print(table, end="")
            if env.get("GITHUB_STEP_SUMMARY"):
                with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
                    summary.write(f"### The tests main failed\n\n{table}\n")
            return 0
        print("\n".join(misses.report(github, misses.workflow(env), args.days)))
        return 0
    except (Refused, Unreadable, RuntimeError, subprocess.CalledProcessError) as error:
        said = getattr(error, "stderr", None) or error
        print(f"repo_standard misses: {said}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["misses"]:
        return _misses(argv[1:])
    if argv[:1] == ["floor"]:
        argparse.ArgumentParser(
            prog="repo-standard floor",
            description="Print this python3's version and the standard's python3 floor.",
        ).parse_args(argv[1:])
        found = ".".join(map(str, sys.version_info[:3]))
        print(f"python3 {found}, at or past the floor {'.'.join(map(str, PYTHON))}")
        return 0
    if argv[:1] == ["stacks"]:
        parser = argparse.ArgumentParser(prog="repo-standard stacks", description=stacks.__doc__)
        parser.add_argument("verb", choices=stacks.VERBS, help="the target to run")
        parser.add_argument("rest", nargs="*", help="test: the ids to run; select: the base")
        parser.add_argument("--shard", help="test: run part K/N of the whole suite")
        args = parser.parse_intermixed_args(argv[1:])
        shard = ["--shard", args.shard] if args.shard is not None else []
        try:
            root = _root(None)
            return stacks.main(root, load(root), [args.verb, *shard, *args.rest])
        except (Refused, Unreadable) as refused:
            print(f"repo_standard stacks: {refused}", file=sys.stderr)
            return 2
    if argv[:1] == ["routes"]:
        parser = argparse.ArgumentParser(prog="repo-standard routes", description=routes.__doc__)
        parser.add_argument("--producer", required=True, help="prints the real API's routes")
        parser.add_argument("--mock", required=True, help="prints the mock API's routes")
        args = parser.parse_args(argv[1:])
        lines, code = routes.check(args.producer, args.mock)
        print(
            "".join(f"{line}\n" for line in lines), end="", file=sys.stderr if code == 2 else None
        )
        return code
    parser = argparse.ArgumentParser(prog="repo-standard", description=__doc__)
    parser.add_argument("guard", choices=VERBS, help="a guard to run, or conform")
    parser.add_argument("--root", help="the repo's root; by default the checkout here")
    parser.add_argument("--config", help="the config; by default <root>/.repo-standard.yml")
    parser.add_argument("--base", help="borders: the ref the diff is read from")
    parser.add_argument("--labels", default="", help="borders: the pull request's labels, a,b")
    parser.add_argument("--hard", action="store_true", help="borders: fail on any warning")
    parser.add_argument(
        "--upstream", default=conform.UPSTREAM, help="conform, upgrade: where the tags are"
    )
    parser.add_argument("--list", action="store_true", help="conform: print the rules, check none")
    parser.add_argument("--event", help="plan: the event; by default $GITHUB_EVENT_NAME")
    parser.add_argument("--selection", help="plan: the file make select wrote")
    parser.add_argument("--to", type=int, help="upgrade: the version to move the repo to")
    args = parser.parse_args(argv)
    if args.guard == "upgrade" and args.to is None:
        parser.error("upgrade needs --to N, the version to move the repo to")
    if args.guard == "conform" and args.list:
        print("\n".join(conform.listing()))
        return 0
    try:
        root = _root(args.root)
        if args.guard == "green":
            from repo_standard import green

            code, lines = green.main(root)
            print("".join(f"repo-standard green: {one}\n" for one in lines), end="")
            return code
        config = load(root, Path(args.config) if args.config else None)
        if args.guard == "plan":
            event = args.event or os.environ.get("GITHUB_EVENT_NAME", "")
            chosen = None
            if args.selection:
                try:
                    chosen = plan.selected(Path(args.selection).read_text(encoding="utf-8"))
                except OSError as error:
                    raise Unreadable(f"cannot read {args.selection}: {error.strerror}") from error
            outputs = plan.plan(config, event, chosen, root).outputs()
            print("".join(f"{key}={value}\n" for key, value in outputs.items()), end="")
            return 0
        paths = tracked(root)
        if args.guard == "upgrade":
            print("\n".join(upgrade.run(root, config, paths, args.to, args.upstream or None)))
            return 0
        if args.guard == "conform":
            lines, failed = conform.run(root, config, paths, args.upstream or None)
            print("\n".join(lines))
            return 1 if failed else 0
        if args.guard == "borders":
            found = borders.check(root, config, paths, args.base, args.labels)
            print("".join(f"{borders.annotation(one)}\n" for one in sorted(found)), end="")
            return 1 if args.hard and found else 0
        found = {
            "stale": lambda: stale.check(root, config),
            "docs": lambda: docs_true.check(root, config, paths),
            "size": lambda: size.sizes(root, config, paths),
            "comments": lambda: size.comments(root, config, paths),
        }[args.guard]()
    except (Refused, Unreadable) as refused:
        print(f"repo_standard {args.guard}: {refused}", file=sys.stderr)
        return 2
    print("".join(f"{one}\n" for one in sorted(found)), end="")
    return 1 if found else 0
