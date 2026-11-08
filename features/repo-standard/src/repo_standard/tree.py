"""What the guards read of a repo: its files as git lists them, matched against the config's globs,
and the faults they find, printed one to a line."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path


class Unreadable(Exception):
    """git cannot list the tree, or cannot read what a guard asks of it."""


@dataclass(frozen=True, order=True)
class Fault:
    path: str
    line: int | None
    why: str

    def __str__(self) -> str:
        at = f"{self.path}:{self.line}" if self.line else self.path
        return f"{at}: {self.why}"


@cache
def pattern(glob: str) -> re.Pattern[str]:
    """A glob as a pattern over a path from the root: `**` crosses folders, `*` and `?` do not."""
    out, at = [], 0
    while at < len(glob):
        if glob.startswith("**/", at):
            out.append("(?:.*/)?")
            at += 3
        elif glob.startswith("**", at):
            out.append(".*")
            at += 2
        elif glob[at] == "*":
            out.append("[^/]*")
            at += 1
        elif glob[at] == "?":
            out.append("[^/]")
            at += 1
        else:
            out.append(re.escape(glob[at]))
            at += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, globs: tuple[str, ...]) -> bool:
    return any(pattern(glob).match(path) for glob in globs)


def chosen(paths: list[str], files: tuple[str, ...], exclude: tuple[str, ...]) -> list[str]:
    """The paths that one of `files` matches and none of `exclude` does."""
    return [path for path in paths if matches(path, files) and not matches(path, exclude)]


def tracked(root: Path) -> list[str]:
    """Each file git tracks or would track under `root`, as a path from it, that is on disk."""
    command = ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others"]
    listed = subprocess.run([*command, "--exclude-standard"], capture_output=True, text=True)
    if listed.returncode != 0:
        raise Unreadable(f"git cannot list {root}: {listed.stderr.strip()}")
    return sorted({one for one in listed.stdout.split("\0") if one and (root / one).is_file()})
