"""`python -m repo_standard <guard> [--root DIR] [--config FILE]`: run one guard on a repo.

The guards are `borders`, `stale`, `docs`, `size` and `comments`. Each reads the repo's
`.repo-standard.yml`, prints one line for each fault it finds, and exits 1 on any. `borders`
prints each fault as a warning GitHub reads and exits 0 when it warns, or 1 under `--hard`. Every
guard exits 2 when it cannot read the config, the tree or the base: a guard that cannot look never
passes. It uses the standard library only, so CI runs it before any install.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_standard import borders, docs_true, size, stale
from repo_standard.config import Refused, load
from repo_standard.tree import Unreadable, tracked

GUARDS = ("borders", "stale", "docs", "size", "comments")


def _root(given: str | None) -> Path:
    if given:
        return Path(given).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        raise Unreadable(f"not in a git checkout: {top.stderr.strip()}")
    return Path(top.stdout.strip())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m repo_standard", description=__doc__)
    parser.add_argument("guard", choices=GUARDS)
    parser.add_argument("--root", help="the repo's root; by default the checkout here")
    parser.add_argument("--config", help="the config; by default <root>/.repo-standard.yml")
    parser.add_argument("--base", help="borders: the ref the diff is read from")
    parser.add_argument("--labels", default="", help="borders: the pull request's labels, a,b")
    parser.add_argument("--hard", action="store_true", help="borders: fail on any warning")
    args = parser.parse_args(argv)
    try:
        root = _root(args.root)
        config = load(root, Path(args.config) if args.config else None)
        paths = tracked(root)
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
