"""`judge` reverts the one clear culprit of a red main or files its fix row, and `tell` tells the
crew of each culprit jbus reverted.

Both are steps of their own, after `watch.watch`: `watch._retro` reads main and hands its tip, red
after its one rerun, over as `Pass.red`. `jbus.reverts` reads `jbus ci`'s ledger for its flakes and
`tell` sends through `rebase.once`, and `watch` may import neither, since each leads back to it
(`test_jbus_layers.py`). `judge` needs no T3 Code, so a red tip gets its revert or its row in every
pass that `watch` runs in. A revert opened in a pass is told in the same pass, and a message the
outbox held or T3 Code did not take is sent again by a later pass, once, by its mark in
`sent.json`.
"""

from __future__ import annotations

from jbriefs.home import thread_of
from jbus import rebase, reverts, verbs
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import RedTip, _check, _file, checks, when
from jmerge import mainjson
from jmerge import reverts as kept


def judge(run: Pass) -> None:
    """Revert the one clear culprit of the red tip `watch` handed over (`jbus.reverts`), or file
    its fix row, which says why nothing was reverted. A tip whose revert is open, or whose failed
    tests the next pass reads, gets neither yet."""
    if run.red is not None:
        why = kept_why(run, run.red)
        if why is not None:
            _file(run, run.red.slug, run.red.sha, run.red.red, why)


def kept_why(run: Pass, tip: RedTip) -> str | None:
    """Why nothing is reverted for `tip`, or None where no row is to be filed: the revert is open,
    or the next pass judges the tip. Two overlapping reds name every red tip."""
    record = mainjson.load(run.state) or {}
    failed = record.get("failed") if record.get("broken") == tip.sha else None
    landed = when(tip.red[0]["commit"]["committer"]["date"])
    one = reverts.Red(
        tip.sha, [c["sha"] for c in tip.red], tip.pull, tip.culprit, failed, run.now - landed
    )
    branch = str((tip.pull or {}).get("headRefName", ""))
    flakes = reverts.flaky(run, branch) if tip.pull and failed else frozenset[str]()
    made = kept.read(run.state)
    found = reverts.culprit(one, made, flakes)
    if isinstance(found, reverts.Culprit):
        found = reverts.tested(run, found, str(record.get("green", "")), one.age)
    if found == reverts.Keep.OPENED and (stuck := reverts.stuck(run, made[tip.sha], checks)):
        return stuck
    if found in reverts.QUIET:
        return None
    if isinstance(found, reverts.Culprit):
        return None if reverts.revert(run, found) else "jbus could not open its revert"
    if found == reverts.Keep.OVERLAP:
        tips = [c["sha"][:12] for c in tip.red if _check(run, tip.known, c["sha"]) == "failed"]
        return f"{found}, and main is red at {' and '.join(tips)}"
    return str(found)


MESSAGE = (
    "jbus: main went red at {red} when your pull request merged, and stayed red after "
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


def tell(run: Pass, client: Client) -> None:
    """Tell the crew of each revert on record whose message has not gone (`rebase.once`, by its
    mark in `sent.json`). A later pass tries again where it could not go."""
    for one in kept.read(run.state).values():
        thread = thread_of(run.home, one.slug)
        if thread:
            message = MESSAGE.format(red=one.red[:12], revert=one.pull)
            key = rebase.mark("revert", one.slug, one.red[:12])
            rebase.once(run, client, ASK, key, thread, one.slug, message, at=one.red[:12])


STEPS = (
    verbs.Step("tellers", 42, "culprits.judge", lambda half: judge(half.run)),
    verbs.Step(
        "tellers", 45, "culprits.tell", lambda half: tell(half.run, half.client), ("client",)
    ),
)
