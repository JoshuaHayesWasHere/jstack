"""jsettings is jstack's core: it imports no other package of jstack, and every package may import
it. jbus is the top of the tree: no package imports it but jinstall, which installs it.

A package that has to import jbus for now is named in `WAITS`, with what it waits on. The test
fails when one goes and `WAITS` still names it, so the list only shrinks. It is empty: jmerge
reaches jbus's config, queue and act ledger only through its own port (`jmerge.bus`).
"""

import ast
from pathlib import Path

READ_SET = ("features/*/src/",)
ROOT = Path(__file__).resolve().parents[3]
FEATURES = ROOT / "features"
CORE = "jsettings"
TOP = "jbus"
INSTALLS = "jinstall"
WAITS: dict[tuple[str, str], str] = {}


def packages() -> dict[str, Path]:
    """Each package of jstack, by name, and its source directory."""
    return {
        one.name: one
        for one in sorted(FEATURES.glob("*/src/*"))
        if one.is_dir() and (one / "__init__.py").is_file()
    }


def imported(source: Path) -> set[str]:
    """The top-level name of each module the file imports, relative imports aside."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(), str(source))):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module.split(".")[0])
    return found


def importers(of: str) -> set[tuple[str, str]]:
    """Each file of another package that imports `of`, as (package, path in the package)."""
    found = set()
    for name, directory in packages().items():
        if name == of:
            continue
        for source in sorted(directory.rglob("*.py")):
            if of in imported(source):
                found.add((name, str(source.relative_to(directory))))
    return found


def test_the_core_imports_no_other_package_of_jstack():
    others = set(packages()) - {CORE}
    for source in sorted(packages()[CORE].rglob("*.py")):
        assert not imported(source) & others, f"{source} imports {imported(source) & others}"


def test_no_package_but_jinstall_imports_jbus_beyond_what_waits():
    found = {one for one in importers(TOP) if one[0] != INSTALLS}
    assert found <= set(WAITS), f"these import {TOP}: {sorted(found - set(WAITS))}"
    assert found >= set(WAITS), f"these no longer import {TOP}: {sorted(set(WAITS) - found)}"


def test_the_test_sees_an_import_of_jbus(tmp_path):
    source = tmp_path / "one.py"
    source.write_text("import os\nfrom jbus.queue import load\nfrom . import near\n")
    assert imported(source) == {"os", "jbus"}
