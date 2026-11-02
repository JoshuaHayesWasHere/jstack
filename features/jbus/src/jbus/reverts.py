"""`revert` reverts the one clear culprit of a red main, and says why it reverts nothing otherwise.

A red main holds no pull request (`jmerge`, "Main is not red"). Josh chose guess-free reverts on
2026-11-02: once main's tip is red after its one rerun (#672, `watch._check`), jbus reverts the
merge that turned it red only when one culprit is clear, and otherwise files the fix row that a
red main got before (`watch._file`), for the owner to fix.

`culprit` is the rule, a pure function of what `watch._retro` reads of main. One culprit is clear
when the red tip is the merge commit of a briefed pull request and the commit under it was green,
so it is the one merge since the last green. It reverts nothing, and says which `Keep` holds:

- `OVERLAP`: more than one merge since the last green, as when two reds overlap. The fix row names
  every red tip among them.
- `UNBRIEFED`: the tip is no briefed merge's commit, such as a merge by hand.
- `OF_A_REVERT`: the tip is a revert, jbus's or anyone's: a revert that goes red is not reverted.
- `TWICE`: jbus reverted the same slug before, so a row is never reverted twice.
- `FLAKES`: each test that failed at the tip is a flake by `jbus ci`'s rule (`flaky`).

A red tip jbus already opened a revert for is `OPENED`: nothing more is done for it, no row
either, while its revert's pull request goes the normal path. A tip whose failed tests
`mainmoved.tell` has not read yet is `UNREAD`, since a pass runs `watch` before it: the next pass
judges it, and nothing is done for it in this one.

`revert` acts on a clear culprit. `gh pr revert` makes the revert on GitHub, a new commit on a new
branch, so jbus never pushes to main or force-pushes anything. It keeps the revert in
`reverts.json` (`jmerge.reverts`), writes the brief `tasks/<branch>.md` that ties the pull request
to its slug, with the culprit's home, and tells the culprit's crew and its home. `jmerge` merges
the revert by the normal path, its checks green, with no review.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from jbriefs import below
from jbriefs.home import thread_of
from jbus import rebase, write_json
from jbus.ci import facts_of
from jbus.ci.numbers import time
from jbus.passes import Pass
from jbus.t3 import Client
from jmerge import reverts as kept

EVENTS = {"revert": "quiet"}
FLAKE_WINDOW = timedelta(days=7)
"""How far back `flaky` reads `jbus ci`'s ledger for the tests that failed on another branch."""
REVERTED = 'Revert "'
"""How a revert's title starts, GitHub's and jbus's."""


class Keep(enum.StrEnum):
    """Why a red tip of main is not reverted."""

    OPENED = "jbus already opened its revert"
    UNREAD = "the tests that failed there are not read yet"
    OVERLAP = "two reds overlap: more than one merge came since the last green"
    UNBRIEFED = "it is no briefed merge's commit"
    OF_A_REVERT = "it is a revert, and a revert that goes red is not reverted"
    TWICE = "jbus reverted this row before, and a row is never reverted twice"
    FLAKES = "each test that failed there is a flake by jbus ci's rule"


@dataclass(frozen=True)
class Culprit:
    """The one clear culprit of a red tip: the briefed merge whose commit it is."""

    red: str
    slug: str
    pull: dict[str, Any]


@dataclass(frozen=True)
class Red:
    """What `watch._retro` read of a red tip of main, after its one rerun: the tip, the merges
    since the last green, newest first, the briefed pull request merged at the tip and its slug,
    and the tests that failed there, None where `main.json` keeps none for the tip yet."""

    tip: str
    since: Sequence[str]
    pull: dict[str, Any] | None
    slug: str
    failed: Sequence[str] | None


def culprit(red: Red, made: dict[str, kept.Revert], flakes: Collection[str]) -> Culprit | Keep:
    """The rule: the one clear culprit of `red`, or why none is reverted. `made` is every revert
    jbus opened (`jmerge.reverts`), and `flakes` the tests `flaky` names."""
    if red.tip in made:
        return Keep.OPENED
    if len(red.since) > 1:
        return Keep.OVERLAP
    if red.pull is None or not red.slug:
        return Keep.UNBRIEFED
    if red.slug in {one.branch for one in made.values()} or str(
        red.pull.get("title", "")
    ).startswith(REVERTED):
        return Keep.OF_A_REVERT
    if red.slug in {one.slug for one in made.values()}:
        return Keep.TWICE
    if red.failed is None:
        return Keep.UNREAD
    if red.failed and all(test in flakes for test in red.failed):
        return Keep.FLAKES
    return Culprit(red.tip, red.slug, red.pull)


def flaky(run: Pass, branch: str) -> frozenset[str]:
    """The tests `jbus ci` counts as flakes over the last `FLAKE_WINDOW` (`numbers.flaky`'s rule:
    they failed on two branches with no runner fault and no red main to blame), less those that
    failed only on `branch`, the culprit's own: its own red is no flake."""
    facts = facts_of(run.state, run.now)
    since = run.now - FLAKE_WINDOW
    return frozenset(
        test
        for job in facts.jobs
        if job["conclusion"] == "failure"
        and facts.causes.get(job["job"]) == "flake"
        and job["branch"] != branch
        and (time(job["created"]) or since) >= since
        for test in job["tests"] or []
    )


MESSAGE = (
    "jbus: main went red at {red} when your pull request #{number} merged, and stayed red after "
    "its one rerun. It was the one merge since the last green, so jbus opened {revert} to revert "
    "it (Josh's rule of 2026-11-02, guess-free reverts), which merges with no review. Do not push "
    "to the revert's branch. Find the cause in main's failed run at {red}, and bring your change "
    "back in a new pull request with the fix."
)
ASK = rebase.Ask(
    "revert",
    "told the crew",
    "told of the revert",
    MESSAGE,
    refused="T3 Code refused the revert message",
    closes=True,
)


def brief(branch: str, red: Culprit, url: str, home: str) -> str:
    """The brief jbus writes for its revert, which ties the pull request to its slug: its Result
    names the pull request on its `Branch:` line."""
    number = red.pull.get("number")
    return "\n".join(
        [
            f"# {branch}: revert {red.slug} (#{number}), which turned main red at {red.red[:12]}",
            f'Task: "main check failed at {red.red[:12]}" after its one rerun, the one merge since '
            f"the last green (jbus reverts its one clear culprit, Josh's pick of 2026-11-02)",
            "Pull request: opened by jbus with `gh pr revert`",
            "Review: none needed, jmerge merges jbus's revert by the normal path (jmerge.reverts)",
            f"Home: {home}",
            "",
            "## Result",
            "Status: done",
            f"Branch: {branch}   Pull request: {url}",
            "",
        ]
    )


def revert(run: Pass, client: Client | None, red: Culprit) -> bool:
    """Open the revert of `red` and tell its crew and home. Return False where GitHub did not
    open it, so the caller files the fix row instead."""
    url = str(red.pull.get("url", ""))
    asked = run.run(
        "gh",
        "pr",
        "revert",
        url,
        "--body",
        f"jbus reverts this: main went red at {red.red[:12]} and stayed red after its one rerun, "
        "and it was the one merge since the last green.",
    )
    lines = asked.stdout.strip().splitlines()
    opened = lines[-1].strip() if asked.returncode == 0 and lines else ""
    viewed = run.run("gh", "pr", "view", opened, "--json", "url,headRefName,headRefOid")
    try:
        said = json.loads(viewed.stdout) if opened and viewed.returncode == 0 else {}
    except ValueError:
        said = {}
    branch, head = str(said.get("headRefName") or ""), str(said.get("headRefOid") or "")
    if not (branch and head):
        why = (asked.stderr or viewed.stderr or "no answer").strip()
        run.condition(red.slug, f"its revert was not opened: {why}", key=f"revert {red.red}")
        return False
    made = kept.Revert(red.red, red.slug, branch, head, opened)
    path = run.state / kept.NAME
    write_json(
        path,
        {
            **{r: kept.record(one) for r, one in kept.read(run.state).items()},
            red.red: kept.record(made),
        },
    )
    home = below.line(_brief(run, red.slug), "Home:") or "root"
    tasks = run.home / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / f"{branch}.md").write_text(brief(branch, red, opened, home))
    line = f"revert {red.slug}: main red at {red.red[:12]}, jbus opened {opened} to revert it"
    run.find(red.slug, "revert", line, key=f"opened {red.red}")
    run.say(line)
    thread = thread_of(run.home, red.slug)
    if client is not None and thread:
        message = MESSAGE.format(red=red.red[:12], number=red.pull.get("number"), revert=opened)
        key = rebase.mark("revert", red.slug, red.red[:12])
        rebase.once(run, client, ASK, key, thread, red.slug, message, at=red.red[:12])
    return True


def _brief(run: Pass, slug: str) -> str:
    path = run.home / "tasks" / f"{slug}.md"
    return path.read_text(errors="replace") if path.exists() else ""


QUIET = (Keep.OPENED, Keep.UNREAD)
"""The `Keep`s for which a pass files no row: the revert is open, or the next pass judges it."""
