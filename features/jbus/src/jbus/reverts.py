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
either, while its revert's pull request goes the normal path, and `stuck` says when it no longer
does: closed unmerged, in conflict or with a failed check, and the tip gets its row. A tip whose
failed tests `mainmoved.tell` has not read yet is `UNREAD`, since a pass runs `watch` before it:
the next pass judges it, and nothing is done for it in this one. Once the tip is older than
`READ_WAIT` its logs are taken as unreadable, `NOT_READ`, and it gets its row.

`revert` acts on a clear culprit. `gh pr revert` makes the revert on GitHub, a new commit on a new
branch, so jbus never pushes to main or force-pushes anything. It keeps the revert in
`reverts.json` (`jmerge.reverts`), writes the brief `tasks/<branch>.md` that ties the pull request
to its slug, with the culprit's home, and logs a routine event for its home's digest. `tell` tells
the culprit's crew, from every pass until the message goes, so a capped thread or a T3 Code that
gives no answer loses it to nothing. `opened` asks GitHub for the revert's branch first, so a pass
that stopped between GitHub's answer and the record finds its revert and opens no second one, and
the brief is written before the record, so a revert on record has a brief. `jmerge` merges the
revert by the normal path, its checks green, with no review.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from jbriefs import below
from jbus import write_json
from jbus.ci.ledger import JOBS, PULLS
from jbus.ci.ledger import read as ledger
from jbus.ci.numbers import Facts, time
from jbus.passes import Pass
from jmerge import reverts as kept

EVENTS = {"revert": "quiet"}
READ_WAIT = timedelta(hours=1)
"""How long after a red tip landed its failed tests may stay unread, a CI round and its rerun with
room to spare, before they are taken as unreadable."""
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
    NOT_READ = "the tests that failed there could not be read from its logs"


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
    and the tests that failed there, None where `main.json` keeps none for the tip yet, and how
    long ago the tip landed."""

    tip: str
    since: Sequence[str]
    pull: dict[str, Any] | None
    slug: str
    failed: Sequence[str] | None
    age: timedelta = timedelta(0)


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
        return Keep.NOT_READ if red.age > READ_WAIT else Keep.UNREAD
    if red.failed and all(test in flakes for test in red.failed):
        return Keep.FLAKES
    return Culprit(red.tip, red.slug, red.pull)


def flaky(run: Pass, branch: str) -> frozenset[str]:
    """The tests `jbus ci` counts as flakes over the last `FLAKE_WINDOW` (`numbers.flaky`'s rule:
    they failed on two branches with no runner fault and no red main to blame), less those that
    failed only on `branch`, the culprit's own: its own red is no flake."""
    state = run.state
    facts = Facts(
        ledger(state / JOBS), ledger(state / PULLS), ledger(state / "events.jsonl"), run.now
    )
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


FIELDS = "url,headRefName,headRefOid"
"""What `revert` reads of a revert's pull request."""


def opened(run: Pass, red: Culprit) -> dict[str, str]:
    """The revert GitHub already has for `red`, by the branch it names `revert-<number>-<branch>`,
    or nothing."""
    branch = f"revert-{red.pull.get('number')}-{red.pull.get('headRefName')}"
    asked = run.run("gh", "pr", "list", "--state", "open", "--head", branch, "--json", FIELDS)
    try:
        found = json.loads(asked.stdout) if asked.returncode == 0 else []
    except ValueError:
        found = []
    return found[0] if found else {}


def revert(run: Pass, red: Culprit) -> bool:
    """Open the revert of `red`, or take the one GitHub has, and keep it, which `jbus.culprits`
    tells the culprit's crew. Return False where GitHub did not open it, so the caller files the
    fix row instead."""
    said = opened(run, red)
    if not said:
        url = str(red.pull.get("url", ""))
        asked = run.run(
            "gh",
            "pr",
            "revert",
            url,
            "--body",
            f"jbus reverts this: main went red at {red.red[:12]} and stayed red after its one "
            "rerun, and it was the one merge since the last green.",
        )
        lines = asked.stdout.strip().splitlines()
        made = lines[-1].strip() if asked.returncode == 0 and lines else ""
        if not made:
            why = (asked.stderr or "no answer").strip()
            run.condition(red.slug, f"its revert was not opened: {why}", key=f"revert {red.red}")
            return False
        viewed = run.run("gh", "pr", "view", made, "--json", FIELDS)
        try:
            said = json.loads(viewed.stdout) if viewed.returncode == 0 else {}
        except ValueError:
            said = {}
        if not (said.get("headRefName") and said.get("headRefOid")):
            line = f"its revert {made} opened, and GitHub does not say its branch yet"
            run.condition(red.slug, line, key=f"listed {red.red}")
            return True
    branch, head, url = (said.get(key, "") for key in ("headRefName", "headRefOid", "url"))
    home = below.line(_brief(run, red.slug), "Home:") or "root"
    tasks = run.home / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / f"{branch}.md").write_text(brief(branch, red, url, home))
    write_json(
        run.state / kept.NAME,
        {
            **{r: kept.record(one) for r, one in kept.read(run.state).items()},
            red.red: kept.record(kept.Revert(red.red, red.slug, branch, head, url)),
        },
    )
    line = f"revert {red.slug}: main red at {red.red[:12]}, jbus opened {url} to revert it"
    run.find(red.slug, "revert", line, key=f"opened {red.red}")
    run.say(line)
    return True


def stuck(run: Pass, one: kept.Revert, checks: Callable[[dict[str, Any]], str]) -> str:
    """Why the revert on record for a red tip will not merge by itself, or nothing: its pull
    request closed unmerged, conflicts or has a failed check. Nothing where GitHub gives no
    answer, as the next pass asks again."""
    fields = "state,mergeable,statusCheckRollup"
    asked = run.run("gh", "pr", "view", one.pull, "--json", fields)
    try:
        said = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        said = {}
    if said.get("state") == "CLOSED":
        return f"its revert {one.pull} closed unmerged"
    if said.get("state") == "OPEN" and said.get("mergeable") == "CONFLICTING":
        return f"its revert {one.pull} conflicts with main"
    if said.get("state") == "OPEN" and checks(said) == "failed":
        return f"its revert {one.pull} has a failed check"
    return ""


def _brief(run: Pass, slug: str) -> str:
    path = run.home / "tasks" / f"{slug}.md"
    return path.read_text(errors="replace") if path.exists() else ""


QUIET = (Keep.OPENED, Keep.UNREAD)
"""The `Keep`s for which a pass files no row: the revert is open, or the next pass judges it."""
