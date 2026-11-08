"""`repo-standard <verb> [--root DIR] [--config FILE]`: run one guard on a repo, or conform.

`repo-standard` is the command, and `python -m repo_standard` runs the same. The verb `conform`
holds the repo to every rule of the standard (`repo_standard.conform`), prints each fault, waiver
and note, and exits 1 on an error. `--upstream` names the repo whose `repo-standard-vN` tags it
lists for a newer version, and `--list` prints each rule's level and id and checks nothing.

The verb `plan` prints, as `key=value` lines for `$GITHUB_OUTPUT`, what the shared check
workflow's jobs run (`repo_standard.plan`): it reads the config's `check` part, the event from
`--event` or `$GITHUB_EVENT_NAME`, and a pull request's selection from `--selection`, the file
`make select` wrote.

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

from repo_standard import borders, conform, docs_true, plan, size, stale
from repo_standard.config import Refused, load
from repo_standard.tree import Unreadable, tracked

GUARDS = ("borders", "stale", "docs", "size", "comments")
VERBS = (*GUARDS, "conform", "plan")


def _root(given: str | None) -> Path:
    if given:
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        raise Unreadable(f"not in a git checkout: {top.stderr.strip()}")
    return Path(top.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repo-standard", description=__doc__)
    parser.add_argument("guard", choices=VERBS, help="a guard to run, or conform")
    parser.add_argument("--root", help="the repo's root; by default the checkout here")
    parser.add_argument("--config", help="the config; by default <root>/.repo-standard.yml")
    parser.add_argument("--base", help="borders: the ref the diff is read from")
    parser.add_argument("--labels", default="", help="borders: the pull request's labels, a,b")
    parser.add_argument("--hard", action="store_true", help="borders: fail on any warning")
    parser.add_argument("--upstream", default=conform.UPSTREAM, help="conform: where the tags are")
    parser.add_argument("--list", action="store_true", help="conform: print the rules, check none")
    parser.add_argument("--event", help="plan: the event; by default $GITHUB_EVENT_NAME")
    parser.add_argument("--selection", help="plan: the file make select wrote")
    args = parser.parse_args(argv)
    if args.guard == "conform" and args.list:
        print("\n".join(conform.listing()))
        return 0
    try:
        root = _root(args.root)
        config = load(root, Path(args.config) if args.config else None)
        if args.guard == "plan":
            event = args.event or os.environ.get("GITHUB_EVENT_NAME", "")
            chosen = None
            if args.selection:
                try:
                    chosen = plan.selected(Path(args.selection).read_text(encoding="utf-8"))
                except OSError as error:
                    raise Unreadable(f"cannot read {args.selection}: {error.strerror}") from error
            outputs = plan.plan(config.check, event, chosen).outputs()
            print("".join(f"{key}={value}\n" for key, value in outputs.items()), end="")
            return 0
        paths = tracked(root)
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
