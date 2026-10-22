"""`jbus.cli` is the spine of a pass and the command's entry point, and it stops growing.

A feature adds a verb (`verbs.Verb`) or a step (`verbs.Step`) in its own module, and no line
in `jbus.cli`: so the file has at most `LINES` lines, and the modules it imports from jbus
are `IMPORTS` or fewer. `IMPORTS` is what it imported once its second half became slots of
steps, seven fewer than before; a name may leave it, and none may join it, as no verb joins
`verbs.FIRST`. A name that leaves `jbus.cli` leaves `IMPORTS` in the same change, so it
cannot join again unseen.
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
    """Every module of jbus the source imports, by its name under `jbus`."""
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
    assert lines <= LINES, f"features/jbus/src/jbus/cli.py has {lines} lines: a verb or a step goes in its module"


def test_cli_imports_no_module_of_jbus_its_frozen_imports_do_not_name():
    joined = sorted(set(imported(SOURCE.read_text())) - set(IMPORTS))
    assert joined == [], f"features/jbus/src/jbus/cli.py imports {joined}: declare a step or a verb instead"


def test_imports_names_only_what_cli_imports():
    left = sorted(set(IMPORTS) - set(imported(SOURCE.read_text())))
    assert left == [], f"features/jbus/src/jbus/cli.py no longer imports {left}: take them out of IMPORTS"


def test_a_name_that_joins_the_imports_is_found():
    source = SOURCE.read_text().replace("from jbus import (\n", "from jbus import (\n    states,\n")
    assert sorted(set(imported(source)) - set(IMPORTS)) == ["states"]
    assert sorted(set(imported(source + "\nimport jbus.chores\n")) - set(IMPORTS)) == [
        "chores",
        "states",
    ]
