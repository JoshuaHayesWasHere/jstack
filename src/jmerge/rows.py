"""The queue's word on a pull request: whether its row is held, and whether a row it must
merge after has merged. `jbus queue hold` takes a row's go back, and `jbus queue add
--merge-after a,b` names the rows whose pull requests merge first (`jbus.queue`). Both are
columns of the project's `queue.json`, which this module only reads.

A repo that has no jbus config, or that no project of it names, has no queue, and nothing in
it is held or ordered. A queue that cannot be read is another matter: it may hold the very
hold that stops a merge, so `short` then names it, and nothing merges until it is mended.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jbus
from jbus import queue
from jmerge import ready

NO_PULL = "no pull request yet"


@dataclass(frozen=True)
class Migrations:
    """Where a repo keeps its migrations, and whether their names carry a number that is taken
    when they land: the `migrations` and `migration_names` of its project in jbus's config."""

    directory: str
    numbered: bool


def migrations(checkout: Path) -> Migrations | None:
    """The migrations of the project whose checkout this is, none where it names no directory
    or where no config names the project, so a repo that has no migrations is held to nothing."""
    try:
        config = jbus.load()
    except jbus.Refused:
        return None
    project = next(
        (one for one in config.projects if one.checkout.resolve() == checkout.resolve()), None
    )
    if project is None or not project.migrations:
        return None
    return Migrations(project.migrations, project.migration_names == jbus.NUMBERED)


def merge_order(rows: list[queue.Row] | None, slugs: dict[int, str]) -> list[int]:
    """The pull request numbers of `slugs` (number to its brief's slug) in the order they merge in.

    A row merges after the rows it names in `merge_after`, and after the rows those name, also
    through a row that is not in `slugs`. Pull requests of rows with no such order between them
    go by number, the older first. A cycle, which `jbus queue add` refuses, is cut by number.
    """
    table = {row["slug"]: row for row in rows or []}

    def before(slug: str) -> set[str]:
        found: set[str] = set()
        todo = list(table.get(slug, {}).get("merge_after", []))
        while todo:
            one = todo.pop()
            if one not in found:
                found.add(one)
                todo.extend(table.get(one, {}).get("merge_after", []))
        return found

    waits = {number: before(slug) for number, slug in slugs.items()}
    placed: list[int] = []
    left = sorted(slugs)
    while left:
        free = [one for one in left if not {slugs[n] for n in left if n != one} & waits[one]]
        first = free[0] if free else left[0]
        placed.append(first)
        left.remove(first)
    return placed


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
    except (queue.Unparsable, OSError):
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
