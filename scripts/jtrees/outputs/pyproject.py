"""The regions of `pyproject.toml` the manifests write: the commands, the wheel's packages, the
source tree the wheel carries beside them, and the paths pytest and ruff read.

A region is the lines between `# generated: <part> ...` and the next `# end generated`; the
rest of the file is hand-written and is left as it is. hatch reads static lists, so these
are written into the file and not found at build time.
"""

from __future__ import annotations

import json
import re

from jtrees.crawl import Invalid
from jtrees.model import FEATURES, Tree
from jtrees.outputs import catalog

PATH = "pyproject.toml"
REGION = re.compile(
    r"(?P<begin>^# generated: (?P<part>[a-z]+)[^\n]*\n)(?P<body>.*?)(?P<end>^# end generated$)",
    re.S | re.M,
)
PARTS = ("scripts", "packages", "source", "paths", "ruff")
# Where the wheel puts the source tree, under the environment it is installed into (its shared
# data, `<venv>/share/jstack`), a path with no Python version in it: `jbriefs.skills.PACKAGED`
# reads it, and the install assembles each harness's layout from it.
SHARE = "share/jstack"
# The folders skills link into that hold no item: the layout points such a link at GitHub, and
# the release must hold the target to tell it from a link that dangles.
LINKED = ("docs",)


def _list(key: str, values: list[str]) -> str:
    """One entry a line, each with its trailing comma, so two changes to different entries
    change different lines and merge."""
    return f"{key} = [\n" + "".join(f"    {json.dumps(one)},\n" for one in values) + "]\n"


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


def _source(tree: Tree) -> list[str]:
    """What the wheel carries for the install to assemble the layouts from: the catalog and
    plugin.json, each top folder an item or a hook sits in, and the folders of `LINKED` that
    hold a page."""
    paths = [item.path for item in tree.items] + [str(one["path"]) for one in catalog.hooks(tree)]
    linked = {one for one in LINKED if any(p.is_file() for p in (tree.root / one).rglob("*.md"))}
    folders = {path.split("/", 1)[0] for path in paths} | linked
    return [catalog.PATH, "plugin.json", *sorted(folders)]


def _part(tree: Tree, part: str) -> str:
    if part == "scripts":
        listed = sorted(command for feature in tree.features for command in feature.commands)
        return "".join(f'{name} = "{target}"\n' for name, target in listed)
    if part == "packages":
        # By the package's name, which a move leaves as it is: its line changes in place.
        packages = sorted(
            (package for feature in tree.features for package in feature.packages),
            key=lambda package: (package.rsplit("/", 1)[-1], package),
        )
        return _list("packages", packages)
    if part == "source":
        return "".join(
            f"{json.dumps(one)} = {json.dumps(f'{SHARE}/{one}')}\n" for one in _source(tree)
        )
    if part == "paths":
        tests = _tests(tree)
        return _list("testpaths", tests) + _list("pythonpath", _python(tree) + tests)
    return _list("src", _python(tree) + _tests(tree))


def render(tree: Tree) -> dict[str, bytes]:
    text = (tree.root / PATH).read_text(encoding="utf-8")
    found = [one["part"] for one in REGION.finditer(text)]
    if sorted(found) != sorted(PARTS):
        raise Invalid([f"{PATH}: has the regions {found}, not one each of {list(PARTS)}"])
    built = REGION.sub(lambda one: one["begin"] + _part(tree, one["part"]) + one["end"], text)
    return {PATH: built.encode()}
