"""The queue's word on a pull request: whether its row is held, and whether a row it must
merge after has merged. `jbus queue hold` takes a row's go back, and `jbus queue add
--merge-after a,b` names the rows whose pull requests merge first (`jbus.queue`). Both are
columns of the project's `queue.json`, which this module only reads.

A repo that has no jbus config, or that no project of it names, has no queue, and nothing in
it is held or ordered. A queue that cannot be read is another matter: it may hold the very
hold that stops a merge, so `short` then names it, and nothing merges until it is mended.
"""

from __future__ import annotations

from pathlib import Path

import jbus
from jbus import queue
from jmerge import ready

NO_PULL = "no pull request yet"


def read(checkout: Path) -> list[queue.Row] | None:
    """The rows of the queue of the project whose checkout this is, none where it has no
    queue, and None where the queue is there and cannot be read."""
    try:
        config = jbus.load()
    except jbus.Refused:
        return [] if not (jbus.config_dir() / "config.toml").exists() else None
    project = next(
        (one for one in config.projects if one.checkout.resolve() == checkout.resolve()), None
    )
    if project is None:
        return []
    try:
        return queue.load(config.state(project))
    except queue.Unparsable:
        return None


def short(rows: list[queue.Row] | None, slug: str) -> str:
    """What the queue keeps the pull request of the row `slug` from, or nothing.

    A held row comes first. Then the first row it merges after that is not over: a row that
    is `merged` or `done` has nothing left to merge, and a slug with no row is one that was
    removed after it did, which `jbus queue remove` allows only once nothing waits on it.
    """
    if rows is None:
        return ready.QUEUE_UNREADABLE
    table = {row["slug"]: row for row in rows}
    row = table.get(slug)
    if row is None or row.get("status") in queue.FINAL:
        return ""
    if row.get("held"):
        return ready.ROW_HELD
    for other in row.get("merge_after", []):
        ahead = table.get(other)
        if ahead is not None and ahead.get("status") not in queue.FINAL:
            return ready.MERGES_AFTER.format(slug=other, open=ahead.get("pr") or NO_PULL)
    return ""
