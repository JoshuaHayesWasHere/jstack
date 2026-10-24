"""This module keeps a stacked link on its base, and tells its crew when to move it.

A row whose brief builds on another row's code (`--depends`, named on its `Builds on:` line)
launches once that row has opened its pull request, stacked on that pull request's branch
(`dispatch`, `World.stack_on`). Its brief's `Stacked on: <slug> <branch>` line is the one record
of the stack: the crew opens its pull request on that branch, and `jmerge` waits on the line
(`ready.STACKED_ON`).

Each pass reads every open pull request whose brief has the line and has not moved yet:

- While the base is open and its head moved (review fixes, a rebase), the link's crew is told to
  rebase onto the base's branch with "A link that moved", once for each head of the link and head
  of the base, under the key `restack|<slug>|<head 12>|<base head 12>`. A link whose head holds
  the base's head is told nothing: GitHub's compare says so, and the answer is kept under the key
  `stacked|<slug>|<head 12>|<base head 12>` so it is asked once.
- Once the base merged, jbus bases the link's pull request on the default branch, where GitHub
  has not done so itself on deleting the base's branch, and tells the crew to move its own
  commits onto it, from the base's last head, under the key `restack|<slug>|<head 12>|<merge
  12>`. Only once that message went does the line say `Stacked on: <slug> <default> at
  <merge>`, so a message held for a thread at work is sent on a later pass. `jmerge` then waits
  until the link's head holds that commit (`ready.STACKED_UNMOVED`), and merges it as any other.

A base closed with no merge leaves its link waiting on `jmerge`'s line: GitHub closes a pull
request whose base branch is deleted, and what to do with the work is the home's."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from jbus import END_TURN, dispatch, read_json, rebase, verbs
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import World
from jmerge import stacked as stacks

EVENTS = {"restack": "quiet"}
KIND = "restack"
HOLDS = "stacked"
_MOVE = (
    'In your own worktree, read "A link that moved" in the crew skill again, from the file, '
    "and run its block with {was} as the branch it sat on."
)
RESTACK = (
    "jbus: {base}'s branch {branch} moved to {tip} under your stacked pull request #{number}. "
    + _MOVE
    + " "
    + END_TURN
)
MOVED = (
    "jbus: {base} merged as {merge}, and your stacked pull request #{number} is now based on "
    "{default}. "
    + _MOVE
    + " That commit is the head {base} merged at. If the block prints `not found`, run it again "
    "with {branch}. " + END_TURN
)


def move(run: Pass, client: Client, world: World) -> None:
    """Tell the crew of each stacked link whose base moved, once for each move, and base a link
    whose base merged on the default branch."""
    sent = set(read_json(run.state / "sent.json", []))
    default = ""
    for slug, pull in world.open.items():
        head = str(pull.get("headRefOid") or "")
        brief = _brief(run, slug)
        stacked = stacks.of(brief)
        if not head or stacked is None or stacked.at or not rebase.crew(run, slug):
            continue
        base = world.open.get(stacked.slug)
        merged = None if base else world.merged.get(stacked.slug)
        if merged:
            if not default:
                asked = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
                default = asked.stdout.strip().removeprefix("origin/")
            if default:
                _moved(run, client, world, slug, pull, stacked, merged, default, sent)
            else:
                run.say(f"wait {slug}: the default branch is not known, so it is not moved")
        elif base:
            _restack(run, client, world, slug, pull, stacked, base, sent)


def _restack(
    run: Pass,
    client: Client,
    world: World,
    slug: str,
    pull: dict[str, Any],
    stacked: stacks.Stacked,
    base: dict[str, Any],
    sent: set[str],
) -> None:
    head, tip = str(pull["headRefOid"]), str(base.get("headRefOid") or "")
    if not tip or {rebase.mark(kind, slug, head, tip[:12]) for kind in (KIND, HOLDS)} & sent:
        return
    asked = run.run("gh", "api", f"repos/{{owner}}/{{repo}}/compare/{tip}...{head}")
    try:
        status = json.loads(asked.stdout).get("status") if asked.returncode == 0 else None
    except (ValueError, AttributeError):
        status = None
    if status is None:
        run.say(f"wait {slug}: GitHub did not say whether it holds {stacked.slug}'s head")
        return
    if status in ("ahead", "identical"):
        run.box.mark(rebase.mark(HOLDS, slug, head, tip[:12]))
        return
    message = (
        RESTACK.replace("{base}", stacked.slug)
        .replace("{branch}", stacked.branch)
        .replace("{tip}", tip[:12])
        .replace("{was}", stacked.branch)
    )
    _tell(run, client, world, slug, pull, message, tip, f"{stacked.slug} moved to {tip[:12]}")


def _moved(
    run: Pass,
    client: Client,
    world: World,
    slug: str,
    pull: dict[str, Any],
    stacked: stacks.Stacked,
    merged: dict[str, Any],
    default: str,
    sent: set[str],
) -> None:
    head, number = str(pull["headRefOid"]), pull["number"]
    merge = str((merged.get("mergeCommit") or {}).get("oid") or "")
    if not merge or rebase.mark(KIND, slug, head, merge[:12]) in sent:
        return
    if pull.get("baseRefName") not in (None, "", default):
        asked = run.run("gh", "pr", "edit", str(number), "--base", default)
        if asked.returncode:
            said = (asked.stderr or asked.stdout).strip().splitlines()
            why = said[-1] if said else f"gh exited {asked.returncode}"
            run.say(f"wait {slug}: #{number} could not be based on {default}: {why}")
            return
    last = str(merged.get("headRefOid") or "") or stacked.branch
    message = (
        MOVED.replace("{base}", stacked.slug)
        .replace("{merge}", merge[:12])
        .replace("{default}", default)
        .replace("{branch}", stacked.branch)
        .replace("{was}", last)
    )
    if _tell(run, client, world, slug, pull, message, merge, f"{stacked.slug} merged"):
        _rewrite(run, slug, replace(stacked, branch=default, at=merge))


def _tell(
    run: Pass,
    client: Client,
    world: World,
    slug: str,
    pull: dict[str, Any],
    message: str,
    under: str,
    why: str,
) -> bool:
    number, head = pull["number"], str(pull["headRefOid"])
    ask = rebase.Ask(
        KIND,
        "told the crew",
        "told to move its stacked link",
        message,
        head[:12],
        no_thread="stacked link with no thread to tell",
        refused="T3 Code refused the message to move a stacked link",
    )
    if not rebase.post(run, client, world, number, why, ask, under[:12]):
        return False
    run.box.mark(rebase.mark(KIND, slug, head, under[:12]))
    line = f"{KIND} {slug}: told the crew {why} (#{number}, {head[:12]})"
    run.find(slug, KIND, line, message, key=f"{head[:12]} {under[:12]}")
    run.say(line)
    return True


def _brief(run: Pass, slug: str) -> str:
    try:
        return (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        return ""


def _rewrite(run: Pass, slug: str, stacked: stacks.Stacked) -> None:
    """Write where the link sits now on its brief's `Stacked on:` line, read again just before,
    so a line its crew added since is kept."""
    path = run.home / "tasks" / f"{slug}.md"
    try:
        text = path.read_text(errors="replace")
        path.write_text(dispatch.stacked(text, stacked))
    except OSError as error:
        run.say(f"wait {slug}: its Stacked on: line could not be written ({error})")


STEPS = (
    verbs.Step(
        "after-expedite",
        27,
        "stack.move",
        lambda half: move(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
