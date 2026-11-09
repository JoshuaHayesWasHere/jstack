"""`judge` reverts the one clear culprit of a red main or files its fix row, and `tell` tells the
crew of each culprit jbus reverted.

Both are steps of their own, after `watch.retro`, which runs after `mainmoved.tell` in a pass:
`watch.retro` reads main as `main.json` judges it and hands its tip, red after its one rerun,
over as `Pass.red`. `jbus.reverts` reads `jbus ci`'s ledger for its flakes and
`tell` sends through `rebase.once`, and `watch` may import neither, since each leads back to it.
`judge` needs no T3 Code, so a red tip gets its revert or its row in every pass that `watch` runs
in. A revert opened in a pass is told in the same pass, and a message the
outbox held or T3 Code did not take is sent again by a later pass, once, by its mark in
`sent.json`.
"""

from __future__ import annotations

import json

from jbriefs.home import thread_of
from jbus import mainmoved, rebase, reverts, verbs
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import RedTip, _file, checks, when
from jmerge import mainjson
from jmerge import reverts as kept

FIRST = "this is the project's first pass, which reverts nothing"
REMOVED = "{slug}, the merge that turned it red, was removed from the queue"


def judge(run: Pass) -> None:
    """Revert the one clear culprit of the red tip `watch` handed over (`jbus.reverts`), or file
    its fix row, which says why nothing was reverted. A tip whose revert is open, or whose failed
    tests the next pass reads, gets neither yet. On a project's first pass, and for a merge whose
    row was removed, jbus reverts nothing and files the fix row at once: a red main always has
    its row, and no home is woken of it."""
    if run.red is not None:
        if run.first:
            why: str | None = FIRST
        elif run.red.slug and run.red.slug in run.removed:
            why = REMOVED.format(slug=run.red.slug)
        else:
            why = kept_why(run, run.red)
        if why is not None:
            _file(run, run.red.slug, run.red.sha, run.red.red, why)


def kept_why(run: Pass, tip: RedTip) -> str | None:
    """Why nothing is reverted for `tip`, or None where no row is to be filed: the revert is open,
    or the next pass judges the tip. The rule judges the red run's oldest commit, the first red
    since the last green, and reads the tests that failed at each later tip only once that one is
    clear. Two overlapping reds name every red tip."""
    record = mainjson.load(run.state) or {}

    def failed_of(sha: str) -> list[str] | None:
        if record.get("broken") == sha:
            return record.get("failed")
        return mainmoved.failed_at(run, sha) if len(tip.red) > 1 else None

    since = [
        (c["sha"], "failed" if c["sha"] == tip.sha else mainmoved.main_check(run, c["sha"]))
        for c in tip.red
    ]
    oldest = since[-1][0]
    failed = failed_of(oldest) if tip.pull else None
    landed = when(tip.red[0]["commit"]["committer"]["date"])
    one = reverts.Red(since, tip.pull, tip.culprit, failed, run.now - landed, tip.under)
    branch = str((tip.pull or {}).get("headRefName", ""))
    flakes = reverts.flaky(run, branch) if tip.pull and failed else frozenset[str]()
    made = kept.read(run.state)
    found = reverts.culprit(one, made, flakes)
    if isinstance(found, reverts.Culprit):
        under = tip.under or str(record.get("green", ""))
        found = reverts.tested(run, found, under, one.age)
    if isinstance(found, reverts.Culprit):
        found = reverts.covered(found, one, (failed_of(sha) for sha, _ in since[:-1]))
    opened = next((sha for sha, _ in since if sha in made), "")
    if found == reverts.Keep.OPENED and (
        stuck := reverts.stuck(run, made[opened], checks, opened != tip.sha)
    ):
        return stuck
    if found in reverts.QUIET:
        return None
    if isinstance(found, reverts.Culprit):
        return None if reverts.revert(run, found) else "jbus could not open its revert"
    if found == reverts.Keep.OVERLAP:
        tips = [
            c["sha"][:12]
            for c in tip.red
            if c["sha"] == tip.sha or mainmoved.main_check(run, c["sha"]) == "failed"
        ]
        return f"{found}, and main is red at {' and '.join(tips)}"
    return str(found)


MESSAGE = (
    "jbus: main went red at {red} when your pull request merged, and stayed red after "
    "its one rerun. It was the first red since the last green, and no merge on top of it failed "
    "another test, so jbus opened {revert} to revert it (Josh's rule of 2026-11-02, guess-free "
    "reverts), which merges with no review. Do not push to the revert's branch. Find the cause "
    "in main's failed run at {red}, and bring your change back in a new pull request with the fix."
)
ASK = rebase.Ask(
    "revert",
    "told the crew",
    "told of the revert",
    MESSAGE,
    refused="T3 Code refused the revert message",
    closes=True,
)


def tell(run: Pass, client: Client) -> None:
    """Tell the crew of each revert on record whose message has not gone (`rebase.once`, by its
    mark in `sent.json`) and whose pull request is still open. A later pass tries again where it
    could not go. The daily prune forgets the mark of a finished row while its record stays, so a
    revert GitHub says is no longer open is marked again and not told; one GitHub gives no
    answer for waits for the next pass."""
    for one in kept.read(run.state).values():
        thread = thread_of(run.home, one.slug)
        key = rebase.mark("revert", one.slug, one.red[:12])
        if not thread or key in run.box.sent():
            continue
        state = _state(run, one.pull)
        if state == "OPEN":
            message = MESSAGE.format(red=one.red[:12], revert=one.pull)
            rebase.once(run, client, ASK, key, thread, one.slug, message, at=one.red[:12])
        elif state:
            run.box.mark(key)


def _state(run: Pass, pull: str) -> str:
    """The state GitHub gives the pull request, `OPEN`, `MERGED` or `CLOSED`, or nothing where it
    gives no answer."""
    asked = run.run("gh", "pr", "view", pull, "--json", "state")
    try:
        said = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        said = {}
    return str(said.get("state") or "") if isinstance(said, dict) else ""


STEPS = (
    verbs.Step("after-expedite", 12, "culprits.judge", lambda half: judge(half.run)),
    verbs.Step(
        "after-expedite", 14, "culprits.tell", lambda half: tell(half.run, half.client), ("client",)
    ),
)
