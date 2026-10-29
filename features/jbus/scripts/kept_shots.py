"""Fail a pull request whose diff changes a kept shot of the view and any other file.

Only the shots row redraws the kept shots, in a pull request of its own that changes nothing else
(`jbus.shots`). A feature's pull request keeps main's: a shot it changed would conflict with every
other pull request that changed the same shot, and is not the browser's that draws them.

    python3 features/jbus/scripts/kept_shots.py --base HEAD^1

It prints an `::error::` line GitHub reads as an annotation for each file that may not be beside
the shots, and exits 1. It exits 0 on a diff that changes no kept shot, or only kept shots, and 2
when git cannot read the diff. The borders check runs it, with no uv sync, so it loads
`jbus/shots.py` by its path and uses the standard library only."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOTS = ROOT / "features" / "jbus" / "src" / "jbus" / "shots.py"


def load():
    spec = importlib.util.spec_from_file_location("kept_shots_rule", SHOTS)
    rule = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rule)
    return rule


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the commit the diff is read from")
    args = parser.parse_args(argv)
    ran = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "--no-renames", args.base, "HEAD"],
        capture_output=True,
        text=True,
    )
    if ran.returncode:
        print(f"kept shots: git could not read the diff from {args.base}: {ran.stderr.strip()}")
        return 2
    rule = load()
    others = rule.mixed(ran.stdout.splitlines())
    for path in others:
        print(
            f"::error file={path}::this pull request changes a kept shot under {rule.KEPT}/ and "
            f"{path}: leave the shots as main has them, and the shots row redraws them once it "
            "merged"
        )
    return 1 if others else 0


if __name__ == "__main__":
    sys.exit(main())
