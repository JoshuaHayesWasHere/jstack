"""`tell` tells the crew of each open pull request a merged rule breaks, in the pass that reads the
merge.

#1702 merged a new rule at 01:16Z on 2026-11-12, and #1711, #1712, #1713 and #1716 each found
the red alone within the half hour. Now `jmerge` runs a pull request's new or tightened tests on
each open pull request merged with it before it merges, and holds it until it carries the fix or
its Result names each one they fail (`jmerge.preflight`). It then merges with a note on its
`merged` line, `its tests <tests> fail on #<n> ... merged with it, whose crews jbus tells`
(`jmerge.lines.breaks_of`), and `tell` sends each one's crew one message: what merged, the tests,
and to rebase and fix.

`rule-breaks.json` keeps each such merge, written before any send so a pass that stops partway
loses none, until each named pull request's crew is told or the pull request is no longer open:
the merge tick's `jmerge` prints its `merged` line once, and no pass sees it, so the tick keeps it
here for the next pass (`keep`), as `jbus.reload` does. A message goes under the key
`rule-breaks|<slug>|<head 12>|<merge 12>` (`rebase.post`), so a crew hears of one merge once a
head, and of a second rule that breaks the same head once more. A pull request with no crew to
tell is said in the pass, and dropped from the merge's list.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from jbus import END_TURN, crewthread, locked, read_json, rebase, record, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import World
from jmerge import lines as lines_of

if TYPE_CHECKING:
    from jbus.poll import Half

FILE = "rule-breaks.json"
LOCK = "rule-breaks.lock"
KIND = "rule-breaks"
EVENTS = {"rule-breaks": "quiet"}
TOLD = (
    "jbus: pull request #{merged} merged at {commit} with tests your pull request #{number} fails "
    "merged with it: {tests}. Its crew named yours rather than change the rule, so the change is "
    'yours to make: rebase onto the default branch with the crew skill\'s "A conflict" block, '
    "run with `stale`, run the check command, fix what fails, and push with the block's push. "
)


def owed(run: Pass, said: Iterable[str]) -> list[dict[str, Any]]:
    """The merges whose broken pull requests' crews are still to be told: those kept in
    `rule-breaks.json`, and each `merged` line of `said` that names any."""
    kept: list[dict[str, Any]] = read_json(run.state / FILE, [])
    for text in said:
        line = lines_of.one(text)
        tests, numbers = lines_of.breaks_of(text)
        if line is None or line.word != "merged" or not numbers:
            continue
        commit = text.split()[3]
        if all(one["commit"] != commit for one in kept):
            at = record.stamp(run.now)
            kept.append(
                {
                    "number": line.number,
                    "commit": commit,
                    "tests": list(tests),
                    "breaks": list(numbers),
                    "at": at,
                }
            )
    return kept


def keep(run: Pass, said: Iterable[str]) -> None:
    """Keep each merge of `said` that names pull requests it breaks, for the next pass's `tell`."""
    with locked(run.state, LOCK):
        kept = owed(run, said)
        if kept != read_json(run.state / FILE, []):
            write_json(run.state / FILE, kept)


def tell(run: Pass, client: Client, world: World, said: Iterable[str]) -> None:
    """Tell each crew a kept merge broke, once a head, and keep what is left owed."""
    with locked(run.state, LOCK):
        kept = owed(run, said)
        if not kept:
            return
        write_json(run.state / FILE, kept)
    left = [one for one in (_told(run, client, world, merge) for merge in kept) if one]
    read = {one["commit"] for one in kept}
    with locked(run.state, LOCK):
        added = [one for one in read_json(run.state / FILE, []) if one["commit"] not in read]
        write_json(run.state / FILE, left + added)


def _told(run: Pass, client: Client, world: World, merge: dict[str, Any]) -> dict[str, Any] | None:
    """Tell each crew of `merge` not told yet, and return the merge with those still owed, or
    None once none is."""
    slugs = {pull["number"]: slug for slug, pull in world.open.items()}
    commit, number = merge["commit"], merge["number"]
    tests = " ".join(merge["tests"])
    owes = []
    for broken in merge["breaks"]:
        slug = slugs.get(broken, "")
        if not slug:
            continue
        head = str(world.open[slug].get("headRefOid", ""))
        if rebase.mark(KIND, slug, head, commit[:12]) in run.box.sent():
            continue
        if not crewthread.tended(run, slug):
            run.say(f"wait {slug}: #{broken} has no crew to tell that #{number} breaks it")
            continue
        message = TOLD.format(merged=number, commit=commit[:12], number=broken, tests=tests)
        message = message.replace("{", "{{").replace("}", "}}")
        ask = rebase.Ask(KIND, f"told #{number} breaks it", "told of a rule", message + END_TURN)
        reason = f"#{number} merged at {commit[:12]} with tests it fails: {tests}"
        went = rebase.post(run, client, world, broken, reason, ask, commit[:12])
        if went:
            line = f"{KIND} {slug}: told the crew that #{number} breaks #{broken} ({head[:12]})"
            run.find(slug, KIND, line, went[2], key=f"{commit[:12]} {head[:12]}")
            run.say(line)
        else:
            owes.append(broken)
    return {**merge, "breaks": owes} if owes else None


def _step(half: Half) -> None:
    """Run `tell` where the pass could ask T3 Code and GitHub, and `keep` where it could not."""
    world = half.seen.world
    if world is not None and half.client is not None:
        tell(half.run, half.client, world, half.said)
    else:
        keep(half.run, half.said)


STEPS = (verbs.Step("tellers", 76, "rulebreaks.tell", _step),)
