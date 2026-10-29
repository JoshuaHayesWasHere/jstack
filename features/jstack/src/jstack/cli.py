"""`jstack <name> [args...]`: run a feature's command, as `j<name> [args...]` runs it.

`table.COMMANDS` names each feature's command by the name typed after `jstack`, and the
function its console script runs. `scripts/generate-jstack-trees.py` writes it from each
`features/*/feature.json`'s `commands`, so a new command needs no line here. `main` imports
the one module of the name typed and nothing of any other feature, so `jstack <name>` starts
as fast as `j<name>` does. It sets `sys.argv` as the command's own script would, so its usage,
its `--help` and its exit code are the command's own.

    0  `jstack --help`, or what the command exited with
    2  no name, or a name the table does not have
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from jstack.table import COMMANDS


def usage() -> str:
    width = max(map(len, COMMANDS))
    rows = "".join(f"  {name:<{width}}  runs {one}\n" for name, (one, _) in COMMANDS.items())
    return (
        "usage: jstack <name> [args...]\n\n"
        "Run a feature's command: `jstack <name> ...` runs `j<name> ...`.\n\n"
        f"names:\n{rows}"
    )


def main(argv: Sequence[str] | None = None) -> int | None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["-h"], ["--help"]):
        print(usage(), end="")
        return 0
    if not argv or argv[0] not in COMMANDS:
        said = f"jstack: no command {argv[0]!r}\n" if argv else ""
        print(f"{said}{usage()}", end="", file=sys.stderr)
        return 2
    command, target = COMMANDS[argv[0]]
    module, function = target.split(":")
    sys.argv = [command, *argv[1:]]
    return getattr(importlib.import_module(module), function)(argv[1:])
