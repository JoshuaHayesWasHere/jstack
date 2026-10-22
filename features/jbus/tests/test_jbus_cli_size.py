"""`jbus.cli` runs a pass and is the command's entry point, and this test keeps the file from
growing.

A feature adds a verb (`verbs.Verb`) or a step (`verbs.Step`) in its own module, and adds no line to
`jbus.cli`. So the file has at most `LINES` lines, and the modules it imports from jbus are
`IMPORTS` or fewer. `IMPORTS` lists what `jbus.cli` imported after the second half of its pass
became steps in slots. That is seven modules fewer than before. A change may remove a name from
`IMPORTS` but not add one, just as no change adds a verb to `verbs.FIRST`. A change that removes a
name from `jbus.cli` also removes it from `IMPORTS`, so this test catches a change that adds the
name back.
"""

import ast
from pathlib import Path

from jbus import cli

LINES = 300
IMPORTS = (
    "alert",
    "archived",
    "dispatch",
    "expedite",
    "merge",
    "questions",
    "queue",
    "record",
    "rotation",
    "signin",
    "t3",
    "threads",
    "verbs",
    "waiting",
    "wake",
    "watch",
    "work",
)
SOURCE = Path(cli.__file__)


def imported(source: str) -> list[str]:
    """Return every module of jbus that the source imports, by its name under `jbus`."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "jbus":
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("jbus."):
            names.append(node.module.removeprefix("jbus."))
        elif isinstance(node, ast.Import):
            names += [one.name[5:] for one in node.names if one.name.startswith("jbus.")]
    return names


def test_cli_has_at_most_its_lines():
    lines = SOURCE.read_text().count("\n")
    assert lines <= LINES, (
        f"features/jbus/src/jbus/cli.py has {lines} lines: a verb or a step goes in its module"
    )


def test_cli_imports_no_module_of_jbus_its_frozen_imports_do_not_name():
    joined = sorted(set(imported(SOURCE.read_text())) - set(IMPORTS))
    assert joined == [], (
        f"features/jbus/src/jbus/cli.py imports {joined}: declare a step or a verb instead"
    )


def test_imports_names_only_what_cli_imports():
    left = sorted(set(IMPORTS) - set(imported(SOURCE.read_text())))
    assert left == [], (
        f"features/jbus/src/jbus/cli.py no longer imports {left}: take them out of IMPORTS"
    )


def test_a_name_that_joins_the_imports_is_found():
    source = SOURCE.read_text().replace("from jbus import (\n", "from jbus import (\n    states,\n")
    assert sorted(set(imported(source)) - set(IMPORTS)) == ["states"]
    assert sorted(set(imported(source + "\nimport jbus.chores\n")) - set(IMPORTS)) == [
        "chores",
        "states",
    ]
