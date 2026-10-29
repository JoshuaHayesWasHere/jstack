"""The table `jstack` runs each feature's command from: `features/jstack/src/jstack/table.py`.

Each command a manifest declares in `commands` is a row, by its name less a leading `j`, with
the command and the function its console script runs. `jstack`'s own command is not a row. The
table holds no description, so only a new, renamed or moved command changes it, and an edit
to another feature's description leaves jstack's folder as it is.
"""

from __future__ import annotations

from jtrees.crawl import Invalid
from jtrees.model import Tree

PATH = "features/jstack/src/jstack/table.py"
OWN = "jstack"
HEAD = (
    '"""The command each name after `jstack` runs, and the function its console script runs.\n\n'
    "scripts/generate-jstack-trees.py writes this file from each features/*/feature.json's\n"
    '`commands`: edit those, then run it again."""\n\n'
)


def render(tree: Tree) -> dict[str, bytes]:
    rows: dict[str, tuple[str, str]] = {}
    faults = []
    for feature in tree.features:
        for command, target in feature.commands:
            if command == OWN:
                continue
            name = command.removeprefix("j")
            if name in rows:
                faults.append(f"{command}: jstack {name} is also {rows[name][0]}")
            rows[name] = (command, target)
    if faults:
        raise Invalid(faults)
    body = "".join(f'    "{name}": ("{c}", "{t}"),\n' for name, (c, t) in sorted(rows.items()))
    return {PATH: f"{HEAD}COMMANDS = {{\n{body}}}\n".encode()}
