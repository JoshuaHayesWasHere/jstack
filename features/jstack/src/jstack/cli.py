"""`jstack <name> [args...]`: run a feature's command, as `j<name> [args...]` runs it.

`table.COMMANDS` names each feature's command by the name typed after `jstack`, and the
function its console script runs. `scripts/generate-jstack-trees.py` writes it from each
`features/*/feature.json`'s `commands`, so a new command needs no line here. `main` imports
the one module of the name typed and nothing of any other feature, so `jstack <name>` starts
as fast as `j<name>` does. It sets `sys.argv` as the command's own script would while the
command runs, so its usage, its `--help` and its exit code are the command's own.

    0  `jstack --help`, or what the command exited with
    2  no name, or a name the table does not have
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence

from jstack.table import COMMANDS


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="jstack",
        description="Run a feature's command: `jstack <name> ...` runs `j<name> ...`.",
    )
    made.add_argument("name", choices=list(COMMANDS), help="the command, with no leading j")
    return made


def main(argv: Sequence[str] | None = None) -> int | None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        parser().parse_args(argv[:1])
    command, target = COMMANDS[argv[0]]
    module, function = target.split(":")
    run = getattr(importlib.import_module(module), function)
    saved, sys.argv = sys.argv, [command, *argv[1:]]
    try:
        return run(argv[1:])
    finally:
        sys.argv = saved
