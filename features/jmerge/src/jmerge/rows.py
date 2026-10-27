from __future__ import annotations

from collections.abc import Sequence
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


def base_red(base: str, runs: list[dict], slug: str, text: str = "") -> str:
    """The red hold of a pull request into an integration branch. It holds when a check of the
    branch's tip ended without passing on its latest run, as GitHub's check runs list them
    (`failed`). A cancelled run is no failed check, as on main (`jbus.watch.NOT_RED`).

    It does not hold a fix of a red main, as `red` does not, nor the fix of this branch's red at
    its tip: the row jbus files for it (`integration_fix`, `jbus.sidered.integration_branches`),
    or a row whose brief `text` names that red (`fixes`). A fix of another red is held. `failed`,
    `latest`, `integration_fix` and `fixes` are at the end of this module.
    """
    red = failed(runs)
    sha = str(red[0].get("head_sha"))[: mainjson.SHA] if red else ""
    fix = mainjson.fix_of(slug) or slug == integration_fix(base, sha) or fixes(text) == (base, sha)
    if not red or fix:
        return ""
    return ready.BASE_RED.format(base=base, sha=sha)


def ordered(rows: list[queue.Row] | None) -> set[str]:
    """The slugs of the rows that are not over and name a row they merge after: the only rows
    whose commits, carried by another pull request, can hold that one back."""
    return {
        row["slug"]
        for row in rows or []
        if row.get("status") not in queue.FINAL and row.get("merge_after")
    }


def short(
    rows: list[queue.Row] | None, slug: str, carries: Sequence[tuple[str, int, bool]] = ()
) -> str:
    """Why the pull request of `slug` waits on the queue, or nothing. `carries` holds the open
    pull requests that a merge of this one may land, each as its slug, its number and whether
    its head could be read: one whose commits this head contains and its base does not. This
    one waits on their rows' `merge_after` as on its own, and on one it could not read."""
    if rows is None:
        return ready.QUEUE_UNREADABLE
    table = {row["slug"]: row for row in rows}
    row = table.get(slug, {})
    if row.get("status") in queue.FINAL:
        return ""
    if row.get("held"):
        return ready.ROW_HELD
    for other in row.get("merge_after", []):
        ahead = table.get(other)
        if ahead is not None and ahead.get("status") not in queue.FINAL:
            return ready.MERGES_AFTER.format(slug=other, open=ahead.get("pr") or NO_PULL)
    for carried, number, read in carries:
        under = table.get(carried, {})
        if under.get("status") in queue.FINAL:
            continue
        for other in under.get("merge_after", []):
            ahead = table.get(other)
            if other == slug or ahead is None or ahead.get("status") in queue.FINAL:
                continue
            if not read:
                return ready.CARRIES_UNKNOWN.format(carried=carried, number=number)
            return ready.CARRIES_AFTER.format(
                carried=carried, number=number, slug=other, open=ahead.get("pr") or NO_PULL
            )
    return ""


INTEGRATION_FIX = "integration-red-"
"""The start of the slug of a fix row jbus files for a red integration branch
(`jbus.sidered.integration_branches`)."""
FIXES = "Fixes red:"
"""The head line of a brief whose row fixes a red integration branch, `Fixes red: <branch> at
<sha>`, with at least the first 12 characters of the red tip."""
_KEPT = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")


def integration_fix(branch: str, sha: str) -> str:
    """The slug of the fix row for the red of `branch` at `sha`, or with no `sha` the start that
    every fix row of the branch shares."""
    kept = "".join(one if one in _KEPT else " " for one in branch.lower())
    stem = "-".join(kept.split()).strip("-.") or "branch"
    return f"{INTEGRATION_FIX}{stem}-{sha[: mainjson.SHA]}"


def fixes(text: str) -> tuple[str, str] | None:
    """The branch and the red tip, to 12 characters, that the brief's `FIXES` line names in its
    head, or nothing."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(FIXES):
            words = line.removeprefix(FIXES).split()
            if len(words) == 3 and words[1] == "at" and len(words[2]) >= mainjson.SHA:
                return words[0], words[2][: mainjson.SHA]
    return None


def latest(runs: list[dict]) -> list[dict]:
    """The latest run of each check, as GitHub's check runs of a commit list them."""
    found: dict[str, dict] = {}
    for one in sorted(runs, key=lambda run: str(run.get("started_at") or "")):
        found[str(one.get("name"))] = one
    return list(found.values())


def failed(runs: list[dict]) -> list[dict]:
    """The checks whose latest run ended without passing. A cancelled run is no failed check,
    as on main (`jbus.watch.NOT_RED`)."""
    return [
        one
        for one in latest(runs)
        if one.get("status") == "completed" and one.get("conclusion") not in NOT_RED
    ]


BROWSER_FIX = "browser-red-"
"""The start of the slug of the fix row jbus files for main's red browser run
(`jbus.watch.BROWSER`)."""


def browser_red(head: str, slug: str, runs: list[dict], default: str) -> str:
    """The hold on a pull request whose own browser run failed at `head`. The red is main's where
    main's last browser run failed too (`main_browser_red`, of `runs`, main's browser.yml runs as
    GitHub lists them), and it waits as for a red main, unless it is the fix of that red, the row
    jbus files for it (`BROWSER_FIX`). Otherwise the red is the pull request's own, which jbus
    tells its crew (`jbus.expedite.TABLE`)."""
    red = "" if slug.startswith(BROWSER_FIX) else main_browser_red(runs, default)
    if red:
        return ready.MAIN_RED.format(sha=red[: mainjson.SHA])
    return ready.BROWSER_RED.format(head=head[: mainjson.SHA])


def main_browser_red(runs: list[dict], default: str) -> str:
    """The commit of main's last browser run where it failed, or nothing. `runs` are the
    workflow's completed runs: a pull request's run, or a run on another branch than `default`,
    says nothing of main, and a cancelled or skipped one judged no code (`jbus.watch.NOT_RED`)."""
    ran = [
        one
        for one in runs
        if one.get("event") != "pull_request"
        and one.get("head_branch") == default
        and one.get("status") == "completed"
        and one.get("conclusion") not in ("cancelled", "skipped")
    ]
    last = max(ran, key=lambda one: str(one.get("created_at") or ""), default=None)
    if last is None or last.get("conclusion") in NOT_RED:
        return ""
    return str(last.get("head_sha") or "")
