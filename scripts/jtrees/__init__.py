"""jtrees: the files jstack generates from its features, and the check that they are current.

`main` crawls `features/` once (`crawl`), renders each output (`outputs`), and either writes
every file that differs or, with `--check`, writes nothing and names each one that is stale.
It needs only the standard library, since it runs before `uv sync`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jtrees import check
from jtrees.crawl import Invalid, crawl
from jtrees.outputs import OUTPUTS

ROOT = Path(__file__).resolve().parents[2]
RUN = "python3 scripts/generate-jstack-trees.py"
SHOWN = 20


def build(root: Path) -> dict[str, bytes]:
    """Every output of the tree at `root`, by its path."""
    tree = crawl(root)
    want: dict[str, bytes] = {}
    for output in OUTPUTS:
        for path, content in output.render(tree).items():
            if path in want:
                raise Invalid([f"{path}: two outputs write it"])
            want[path] = content
    return want


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-jstack-trees.py",
        description="Write skills.json, the generated regions of pyproject.toml and the docs "
        "indexes from features/.",
    )
    parser.add_argument(
        "--check", action="store_true", help="write nothing, and exit 1 naming each stale file"
    )
    args = parser.parse_args(argv)
    try:
        want = build(root)
    except Invalid as invalid:
        for fault in invalid.faults:
            print(f"invalid: {fault}", file=sys.stderr)
        return 2
    if args.check:
        stale = check.diff(want, root)
        if not stale:
            return 0
        for path in stale[:SHOWN]:
            print(f"stale: {path}", file=sys.stderr)
        if len(stale) > SHOWN:
            print(f"and {len(stale) - SHOWN} more", file=sys.stderr)
        print(f"run {RUN} and commit the result", file=sys.stderr)
        return 1
    written = check.write(want, root)
    for path in written:
        print(f"wrote {path}")
    if not written:
        print(f"current: {len(want)} files")
    return 0
