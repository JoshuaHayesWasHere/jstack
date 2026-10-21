"""The regions of `pyproject.toml` the manifests write: the commands, the wheel's packages, the
harness copy the wheel takes whole beside them, and the paths pytest and ruff read.

A region is the lines between `# generated: <part> ...` and the next `# end generated`; the
rest of the file is hand-written and is left as it is. hatch reads static lists, so these
are written into the file and not found at build time.
"""

from __future__ import annotations

import json
import re

from jtrees.crawl import Invalid
from jtrees.model import FEATURES, Tree
from jtrees.outputs import harness

PATH = "pyproject.toml"
REGION = re.compile(
    r"(?P<begin>^# generated: (?P<part>[a-z]+)[^\n]*\n)(?P<body>.*?)(?P<end>^# end generated$)",
    re.S | re.M,
)
PARTS = ("scripts", "packages", "harness", "paths", "ruff")


def _list(values: list[str]) -> str:
    return json.dumps(values)


def _python(tree: Tree) -> list[str]:
    """The directories each package sits in, which pytest puts on its path."""
    return sorted({package.rsplit("/", 1)[0] for f in tree.features for package in f.packages})


def _tests(tree: Tree) -> list[str]:
    """The test folders, which pytest collects and also puts on its path: a test imports a
    module of another folder's tests by its bare name."""
    found = ["tests"] if (tree.root / "tests").is_dir() else []
    found += sorted(
        path.relative_to(tree.root).as_posix() for path in tree.root.glob(f"{FEATURES}/*/tests")
    )
    return found


def _part(tree: Tree, part: str) -> str:
    if part == "scripts":
        listed = sorted(command for feature in tree.features for command in feature.commands)
        return "".join(f'{name} = "{target}"\n' for name, target in listed)
    if part == "packages":
        packages = sorted(package for feature in tree.features for package in feature.packages)
        return f"packages = {_list(packages)}\n"
    if part == "harness":
        return f"{json.dumps(harness.COPY)} = {json.dumps(harness.PACKAGED)}\n"
    if part == "paths":
        tests = _tests(tree)
        return f"testpaths = {_list(tests)}\npythonpath = {_list(_python(tree) + tests)}\n"
    return f"src = {_list(_python(tree) + _tests(tree))}\n"


def render(tree: Tree) -> dict[str, bytes]:
    text = (tree.root / PATH).read_text(encoding="utf-8")
    found = [one["part"] for one in REGION.finditer(text)]
    if sorted(found) != sorted(PARTS):
        raise Invalid([f"{PATH}: has the regions {found}, not one each of {list(PARTS)}"])
    built = REGION.sub(lambda one: one["begin"] + _part(tree, one["part"]) + one["end"], text)
    return {PATH: built.encode()}
