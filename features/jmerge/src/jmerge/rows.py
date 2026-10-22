from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jbus
from jbus import queue
from jmerge import mainjson, ready

NO_PULL = "no pull request yet"
NOT_RED = ("success", "neutral", "skipped", "cancelled")


@dataclass(frozen=True)
class Migrations:
    directory: str
    numbered: bool


def migrations(checkout: Path) -> Migrations | None:
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


def _state(checkout: Path) -> Path | None | bool:
    try:
        config = jbus.load()
    except jbus.Refused:
        return None if not (jbus.config_dir() / "config.toml").exists() else False
    project = next(
        (one for one in config.projects if one.checkout.resolve() == checkout.resolve()), None
    )
    return None if project is None else config.state(project)


def read(checkout: Path) -> list[queue.Row] | None:
    state = _state(checkout)
    if state is False:
        return None
    if state is None:
        return []
    try:
        return queue.load(state)
    except (queue.Unparsable, OSError):
        return None


def main(checkout: Path) -> mainjson.Main:
    state = _state(checkout)
    return mainjson.read(state) if isinstance(state, Path) else mainjson.Main()


def red(main: mainjson.Main, slug: str) -> str:
    if not main.red or mainjson.fix_of(slug):
        return ""
    return ready.MAIN_RED.format(sha=main.red[: mainjson.SHA])


def base_red(base: str, runs: list[dict], slug: str) -> str:
    """The red hold of a pull request into an integration branch. It holds when the latest run
    of a check of the branch's tip, as GitHub's check runs list them, ended and did not pass.
    A cancelled run is no failed check, as on main (`jbus.watch.NOT_RED`). A fix of a red
    main is not held, just as `red` does not hold it."""
    latest: dict[str, dict] = {}
    for one in sorted(runs, key=lambda run: str(run.get("started_at") or "")):
        latest[str(one.get("name"))] = one
    failed = [
        one
        for one in latest.values()
        if one.get("status") == "completed" and one.get("conclusion") not in NOT_RED
    ]
    if not failed or mainjson.fix_of(slug):
        return ""
    return ready.BASE_RED.format(base=base, sha=str(failed[0].get("head_sha"))[: mainjson.SHA])


def short(rows: list[queue.Row] | None, slug: str) -> str:
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
