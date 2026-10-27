"""This module keeps a stacked link on its base: it moves a link whose base merged itself, and
tells its crew when to move it otherwise.

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
- Once the base merged, jbus bases the link's pull request on the branch the base merged into,
  or on the branch the brief's `Pull request:` line opens it against, where GitHub has not done
  so itself on deleting the base's branch. A base merged into a train leaves its link on that
  train: a rebase onto the default branch would carry the train's commits there. Then jbus moves
  the link's own commits onto that branch itself, in the same pass and with no Claude turn
  (`_carry`): `git rebase --onto origin/<branch> <base's last head>` in a scratch worktree of its
  own, never the crew's, and a push with `--force-with-lease` at the head it read. The crew's
  worktree, where it has one on the branch, is moved to the pushed head with `git reset --keep`.
  jbus moves nothing while the crew's thread is at work, while a reviewer it launched has written
  no review, or while its worktree has work in it (uncommitted, unpushed or a rebase not
  finished); a rebase that conflicts or a push the lease refuses leaves the branch as it was.
  For each of those but a thread at work, which waits for a later pass, jbus tells the crew to
  move its own commits instead, from the base's last head, under the key
  `restack|<slug>|<head 12>|<merge 12>`. Only once the link moved or that message went does the
  line say `Stacked on: <slug> <branch> at <merge>`, so a message held for a capped thread is
  sent on a later pass. `jmerge` then waits until the link's head holds that commit
  (`ready.STACKED_UNMOVED`), and merges it as any other.

A base closed with no merge leaves its link waiting on `jmerge`'s line: GitHub closes a pull
request whose base branch is deleted, and what to do with the work is the home's."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from jbus import END_TURN, dispatch, read_json, rebase, verbs
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import World, against
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
    "{onto}, so its block rebases onto origin/{onto}. "
    + _MOVE
    + " That commit is the head {base} merged at. If the block prints `not found`, run it again "
    "with {branch}. " + END_TURN
)


def move(run: Pass, client: Client, world: World) -> None:
    """Tell the crew of each stacked link whose base moved, once for each move, and base a link
    whose base merged on the branch it merged into, or the one its brief names."""
    sent = set(read_json(run.state / "sent.json", []))
    for slug, pull in world.open.items():
        head = str(pull.get("headRefOid") or "")
        brief = _brief(run, slug)
        stacked = stacks.of(brief)
        if not head or stacked is None or stacked.at or not rebase.crew(run, slug):
            continue
        base = world.open.get(stacked.slug)
        merged = None if base else world.merged.get(stacked.slug)
        if merged:
            onto = _onto(run, brief, merged)
            if onto:
                _moved(run, client, world, slug, pull, stacked, merged, onto, sent)
            else:
                run.say(f"wait {slug}: GitHub did not say what {stacked.slug} merged into")
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
    onto: str,
    sent: set[str],
) -> None:
    head, number = str(pull["headRefOid"]), pull["number"]
    merge = str((merged.get("mergeCommit") or {}).get("oid") or "")
    if not merge or rebase.mark(KIND, slug, head, merge[:12]) in sent:
        return
    if pull.get("baseRefName") not in (None, "", onto):
        asked = run.run("gh", "pr", "edit", str(number), "--base", onto)
        if asked.returncode:
            said = (asked.stderr or asked.stdout).strip().splitlines()
            why = said[-1] if said else f"gh exited {asked.returncode}"
            run.say(f"wait {slug}: #{number} could not be based on {onto}: {why}")
            return
    if rebase.held(run, client, world, slug, number, head):
        return
    last = str(merged.get("headRefOid") or "")
    moved = _carry(run, slug, pull, last, merge, onto) if last else ""
    if moved:
        run.box.mark(rebase.mark(KIND, slug, head, merge[:12]))
        line = (
            f"{KIND} {slug}: moved its own commits onto {onto} once {stacked.slug} merged "
            f"(#{number}, {head[:12]} to {moved[:12]})"
        )
        run.find(slug, KIND, line, key=f"{head[:12]} {merge[:12]}")
        run.say(line)
        _rewrite(run, slug, replace(stacked, branch=onto, at=merge))
        return
    last = last or stacked.branch
    message = (
        MOVED.replace("{base}", stacked.slug)
        .replace("{merge}", merge[:12])
        .replace("{onto}", onto)
        .replace("{branch}", stacked.branch)
        .replace("{was}", last)
    )
    if _tell(run, client, world, slug, pull, message, merge, f"{stacked.slug} merged"):
        _rewrite(run, slug, replace(stacked, branch=onto, at=merge))


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


def _carry(run: Pass, slug: str, pull: dict[str, Any], last: str, merge: str, onto: str) -> str:
    """Move the link's own commits, those above `last`, onto `origin/<onto>`, and push them over
    the head the pass read. Return the head the branch is at now, or nothing when it was left as
    it was, with the reason said."""
    head, number = str(pull["headRefOid"]), pull["number"]
    branch = str(pull.get("headRefName") or slug)
    if _reviewing(_brief(run, slug)):
        return _left(run, slug, "a reviewer it launched has written no review yet")
    crew = _worktree(run, branch)
    busy = _busy(run, crew, head) if crew else ""
    if busy:
        return _left(run, slug, f"its worktree {busy}")
    run.run("git", "fetch", "-q", "origin", f"+refs/heads/{onto}:refs/remotes/origin/{onto}")
    if run.run("git", "cat-file", "-e", f"{head}^{{commit}}").returncode:
        run.run("git", "fetch", "-q", "origin", f"refs/pull/{number}/head")
    if run.run("git", "merge-base", "--is-ancestor", merge, f"origin/{onto}").returncode:
        return _left(run, slug, f"origin/{onto} does not hold {merge[:12]} here")
    if not run.run("git", "merge-base", "--is-ancestor", merge, head).returncode:
        return head
    if run.run("git", "merge-base", "--is-ancestor", last, head).returncode:
        return _left(run, slug, f"its head does not hold {last[:12]} here")
    scratch = Path(tempfile.mkdtemp(prefix=f"jbus-move-{slug}-"))
    tree = scratch / "tree"
    try:
        made = run.run("git", "worktree", "add", "-q", "--detach", str(tree), head)
        if made.returncode:
            return _left(run, slug, "jbus's scratch worktree could not be made")
        moved = run.run("git", "-C", str(tree), "rebase", "-q", "--onto", f"origin/{onto}", last)
        if moved.returncode:
            run.run("git", "-C", str(tree), "rebase", "--abort")
            return _left(run, slug, f"its commits conflict with origin/{onto}")
        new = run.run("git", "-C", str(tree), "rev-parse", "HEAD").stdout.strip()
    finally:
        run.run("git", "worktree", "remove", "--force", str(tree))
        shutil.rmtree(scratch, ignore_errors=True)
    run.run("git", "update-ref", f"refs/jstack/pre-rebase/{slug}/{head[:12]}", head)
    lease = f"--force-with-lease=refs/heads/{branch}:{head}"
    if run.run("git", "push", "-q", lease, "origin", f"{new}:refs/heads/{branch}").returncode:
        return _left(run, slug, f"origin's {branch} is no longer at {head[:12]}, or did not answer")
    if crew and run.run("git", "-C", str(crew), "reset", "-q", "--keep", new).returncode:
        run.say(f"wait {slug}: its worktree {crew} could not follow the move to {new[:12]}")
    return new


def _left(run: Pass, slug: str, why: str) -> str:
    run.say(f"{KIND} {slug}: jbus left its branch as it was ({why}), so its crew moves it")
    return ""


def _reviewing(brief: str) -> bool:
    """Whether a reviewer the crew launched has not written its review yet: a move would change
    the head under it, and the crew skill's own move waits for it too."""
    return len(rebase._LAUNCHED.findall(brief)) > len(rebase._REVIEWED.findall(brief))


def _worktree(run: Pass, branch: str) -> Path | None:
    """The worktree that has the branch checked out, the crew's, or None."""
    listed = run.run("git", "worktree", "list", "--porcelain").stdout
    for entry in listed.split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in entry.splitlines())
        if fields.get("branch") == f"refs/heads/{branch}" and fields.get("worktree"):
            return Path(fields["worktree"])
    return None


def _busy(run: Pass, tree: Path, head: str) -> str:
    """What in the crew's worktree a move would lose or disturb, or nothing: a head other than
    the pushed one, a change not committed, or a rebase of its own not finished."""
    at = run.run("git", "-C", str(tree), "rev-parse", "HEAD").stdout.strip()
    if at != head:
        return f"is at {at[:12] or 'no commit'}, not at {head[:12]}"
    if run.run("git", "-C", str(tree), "status", "--porcelain").stdout.strip():
        return "has changes not committed"
    gitdir = run.run("git", "-C", str(tree), "rev-parse", "--absolute-git-dir").stdout.strip()
    for left in ("rebase-merge", "rebase-apply", "crew-before-rebase"):
        if not gitdir or (Path(gitdir) / left).exists():
            return "has a rebase of its own not finished"
    return ""


def _onto(run: Pass, brief: str, merged: dict[str, Any]) -> str:
    """Return the branch a link goes on once its base merged: the one its brief's `Pull request:`
    line opens it against, or else the one the base merged into, asked of GitHub. Empty when
    GitHub does not say."""
    named = against(brief)
    if named:
        return named
    asked = run.run("gh", "pr", "view", str(merged["number"]), "--json", "baseRefName")
    try:
        said = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        said = {}
    return str(said.get("baseRefName") or "") if isinstance(said, dict) else ""


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
