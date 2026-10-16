"""The one entry point: `jpack lint <pack>`, `jpack verify <pack> [--repo <checkout>]` and
`jpack stale <pack> [--repo <checkout>] [--rev <rev>] [--days <n>]`.

`lint` runs the one shell lint on the pack's notes. `verify` checks that each citation is
there and says what the note quotes. `stale` lists the notes that cite a file changed since
their pin, and the ones stale long enough to prune. Each prints one line per thing it found
and exits 1, prints nothing and exits 0 for a pack in order, and exits 2 for a folder or a
repo it cannot read. The repo is the checkout the pack is in, unless `--repo` names another.
No model reads anything, and nothing is written.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from jpack import LINT, Refused, stale, verify


def _repo(args: argparse.Namespace) -> Path:
    if args.repo:
        return Path(args.repo)
    found = verify.git(Path(args.pack), "rev-parse", "--show-toplevel")
    if found.returncode:
        raise Refused(f"jpack: {args.pack} is in no git checkout: name one with --repo")
    return Path(found.stdout.strip())


def _lint(args: argparse.Namespace) -> list[str]:
    done = subprocess.run(["sh", str(LINT), args.pack], capture_output=True, text=True)
    if done.returncode == 2:
        raise Refused(done.stderr.strip())
    return done.stdout.splitlines()


def _verify(args: argparse.Namespace) -> list[str]:
    return verify.faults(Path(args.pack), _repo(args))


def _stale(args: argparse.Namespace) -> list[str]:
    repo = _repo(args)
    if verify.git(repo, "rev-parse", "-q", "--verify", f"{args.rev}^{{commit}}").returncode:
        raise Refused(f"jpack: {repo} has no commit {args.rev}")
    return stale.lines(Path(args.pack), repo, datetime.now(UTC), rev=args.rev, days=args.days)


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(prog="jpack", description=__doc__)
    verbs = made.add_subparsers(dest="verb", required=True)
    lint = verbs.add_parser("lint", help="every note is in the index and names its sources")
    lint.set_defaults(run=_lint)
    checked = verbs.add_parser("verify", help="each cited line is there and says the quote")
    checked.set_defaults(run=_verify)
    old = verbs.add_parser("stale", help="the notes citing a file changed since their pin")
    old.add_argument("--rev", default="HEAD", help="the revision read as now (HEAD)")
    old.add_argument(
        "--days", type=int, default=stale.DAYS, help="days stale before prune (%(default)s)"
    )
    old.set_defaults(run=_stale)
    for verb in (lint, checked, old):
        verb.add_argument("pack", help="the pack's folder, as docs/context")
    for verb in (checked, old):
        verb.add_argument("--repo", help="the subject repo's checkout (the pack's own)")
    return made


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        found = args.run(args)
    except Refused as error:
        print(error, file=sys.stderr)
        return 2
    for line in found:
        print(line)
    return 1 if found else 0
