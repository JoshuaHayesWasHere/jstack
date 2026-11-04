"""`reverts.json` keeps each revert jbus opened for a red main, and this module is the one place
that defines the file's format.

`jbus.reverts.revert` is the file's only writer. It opens a revert pull request for the one clear
culprit of a red tip of main (`gh pr revert`) and keeps it here under the red tip, the culprit's
merge commit: the culprit's slug, the revert's branch, its head when it opened and its URL. A red
tip with a record here is not reverted again, and a slug a record names is never reverted twice.

`jmerge` reads the file through `read`. A revert's pull request merges by the normal path, its
required checks green, fresh over main and touching no protected path, with no review: Josh chose
guess-free reverts on 2026-11-02, and a revert puts main back to a commit whose check passed. It is
the revert only while its head is the one jbus opened, or one whose range-diff from it is clean,
as after a merge of main into it: any other push to its branch brings the review back. A file that
is missing or cannot be read holds no revert.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jsettings import store

NAME = "reverts.json"


@dataclass(frozen=True)
class Revert:
    red: str
    """The red tip, the culprit's merge commit."""
    slug: str
    """The culprit's slug."""
    branch: str
    """The revert pull request's branch, and the slug of the brief jbus writes for it."""
    head: str
    """The revert pull request's head when it opened."""
    pull: str
    """The revert pull request's URL."""


_KEYS = ("slug", "branch", "head", "pull")


def read(state: Path) -> dict[str, Revert]:
    """The reverts kept in the project's `state`, by red tip. A record of the wrong shape is
    left out."""
    kept = store.read_json(state / NAME, None)
    found = {}
    for red, one in (kept if isinstance(kept, dict) else {}).items():
        values = tuple(one.get(key) if isinstance(one, dict) else None for key in _KEYS)
        strings = tuple(value for value in values if isinstance(value, str) and value)
        if len(strings) == len(values):
            found[red] = Revert(red, *strings)
    return found


def record(revert: Revert) -> dict[str, str]:
    """The record `read` reads back, by red tip."""
    return {key: getattr(revert, key) for key in _KEYS}


def of_branch(reverts: dict[str, Revert], branch: str) -> Revert | None:
    """The revert jbus opened on `branch`, or None."""
    return next((one for one in reverts.values() if one.branch == branch), None)
