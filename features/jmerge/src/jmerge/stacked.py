"""A brief's `Stacked on:` line, the one record of a link jbus stacked: the row it builds on, the
branch its pull request sits on, and, once that row merged and jbus moved the link onto the
default branch, the commit of that branch that merged it.

jbus writes the line at the launch, `Stacked on: <slug> <its branch>`, and again once the row
merged, `Stacked on: <slug> <default branch> at <commit>` (`jbus.stack`). `jmerge` waits on it
(`ready.STACKED_ON`, `ready.STACKED_UNMOVED`), and the crew skill's blocks read it in sh."""

from __future__ import annotations

import re
from dataclasses import dataclass

LINE = "Stacked on:"
_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Stacked:
    slug: str
    branch: str
    at: str = ""


def of(text: str) -> Stacked | None:
    """The `Stacked on:` line in the head of a brief, above its first `## `, or None."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(LINE):
            words = line.removeprefix(LINE).split()
            if len(words) == 2:
                return Stacked(*words)
            if len(words) == 4 and words[2] == "at" and _COMMIT.fullmatch(words[3]):
                return Stacked(words[0], words[1], words[3])
            return None
    return None


def line(stacked: Stacked) -> str:
    at = f" at {stacked.at}" if stacked.at else ""
    return f"{LINE} {stacked.slug} {stacked.branch}{at}"


def unmoved(text: str) -> bool:
    """Whether a brief is of a link that still sits on its base's branch: its branch holds its
    base's commits and its own, so a rebase onto the default branch would replay them."""
    found = of(text)
    return found is not None and not found.at
