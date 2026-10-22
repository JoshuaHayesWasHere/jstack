"""The tree the generator reads: each feature, what it holds, and who owns a path.

A feature is `features/<name>/`, and owns every path under its folder and no other. The generator
reads a path the feature declares (a package, a page, a hook) from the feature's folder when the
file is there, and from the repo root when it is not. A path under no feature's folder has the repo
itself as its owner (`REPO_OWNERS`), or has no owner. `Tree.owners` gives every owner a path has, so
a check sees both a path with no owner and a path with two owners.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FEATURES = "features"
MANIFEST = "feature.json"
Kind = Literal["skill", "principle", "playbook", "template"]
KINDS: tuple[Kind, ...] = ("skill", "principle", "playbook", "template")


def pattern(glob: str) -> re.Pattern[str]:
    """A row of `REPO_OWNERS` as a regex over a repo-relative path: `dir/**` is the whole
    tree, and otherwise `*` and `?` do not cross a `/`. It refuses a `**` anywhere else."""
    if "**" in glob.removesuffix("/**"):
        raise ValueError(f"{glob}: ** is only the whole tree, at the end after a /")
    if glob.endswith("/**"):
        return re.compile(re.escape(glob[:-2]) + ".*")
    parts = ("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in glob)
    return re.compile("".join(parts))


@dataclass(frozen=True)
class Item:
    """One file a brief, a skill or the runtime finds by name: `skills.json` lists it."""

    name: str
    kind: Kind
    path: str
    feature: str
    description: str = ""
    nameable: bool = False


@dataclass(frozen=True)
class Hook:
    event: str
    script: str
    harnesses: tuple[str, ...]
    matcher: str = ""
    refuses: bool = False


@dataclass(frozen=True)
class Feature:
    name: str
    description: str
    packages: tuple[str, ...] = ()
    commands: tuple[tuple[str, str], ...] = ()
    docs: tuple[str, ...] = ()
    hooks: tuple[Hook, ...] = ()
    status_line: str = ""
    git_hooks: tuple[tuple[str, str], ...] = ()
    project_skills: tuple[tuple[str, str], ...] = ()
    nameable: tuple[str, ...] = ()

    @property
    def folder(self) -> str:
        return f"{FEATURES}/{self.name}"

    def holds(self, path: str) -> bool:
        """Whether `path` is the feature's: under its folder."""
        return path.startswith(f"{self.folder}/")


@dataclass(frozen=True)
class Tree:
    root: Path
    features: tuple[Feature, ...]
    items: tuple[Item, ...]
    repo_owners: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = ()

    def feature(self, name: str) -> Feature:
        return next(one for one in self.features if one.name == name)

    def owners(self, path: str) -> tuple[str, ...]:
        """Every owner of a repo-relative path: a feature's name, or the repo's own owner
        (`INFRA`, `SHARED-DELETE`). A path under a feature's folder is that feature's, and a
        repo row that claims it too is a second owner."""
        found = [one.name for one in self.features if one.holds(path)]
        found += [name for name, rows in self.repo_owners if any(r.fullmatch(path) for r in rows)]
        return tuple(found)

    def of(self, kind: Kind) -> tuple[Item, ...]:
        return tuple(item for item in self.items if item.kind == kind)
