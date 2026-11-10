"""This module moves a stacked link onto the branch its base merged into, or tells its crew to.

A row whose brief builds on another row's code (`--depends`, named on its `Builds on:` line)
launches once that row has opened its pull request, stacked on that pull request's branch
(`dispatch`, `World.stack_on`). A depends is the one way a stack is made: `jbus queue add` refuses
a brief whose own `Stacked on:` line names a row its depends does not. Its brief's
`Stacked on: <slug> <branch>` line is the one record of the stack: the crew opens its pull request
on that branch, and `jmerge` waits on the line (`ready.STACKED_ON`).

While the base is open, a link stays on its stack, and its crew is told nothing whatever the
base's head does: the link is moved once, when the base merged. A `merge_after` order is the
home's word on merging and is kept as it is. Each pass reads every open pull request whose brief
has the line and has not moved yet, and whose base merged:

- jbus bases the link's pull request on the branch the base merged into, or on the branch the
  brief's `Pull request:` line opens it against, where GitHub has not done so itself on deleting
  the base's branch. A base merged into another branch than the default leaves its link on that
  branch: a rebase onto the default branch would carry the branch's commits there.
- Then jbus moves the link's own commits onto that branch itself, in the same pass and with no
  turn of its crew (`_carry`): `git rebase --onto origin/<branch> <base's last head>` in a scratch
  worktree of its own, never the crew's, and a push with `--force-with-lease` at the head it read.
  The crew's worktree, where it has one on the branch, is moved to the pushed head with
  `git reset --keep`.
  A link whose head does not hold the base's last head, since the base took commits after it was
  stacked, is moved from the fork instead (`_fork`), where the base only grew: every head of the
  base that this machine's reflogs record under the link's head is under the base's last head. A
  base whose branch is gone, here and on origin, leaves no reflog, so the commit the link's own
  branch was made at counts as one of those heads, unless the branch it moves onto holds it.
  jbus moves nothing while the outbox holds the crew (`rebase.held`): its thread is at work, waits
  on a test slot, or waits on a review it launched that jmerge says is not written at the head.
  Such a link waits for a later pass, and its crew is told nothing. Nor does jbus move it while a
  reviewer the crew launched has written no review (`review.reviewing`), since a move would change
  the head under it, or while its worktree has work in it (uncommitted, unpushed or a rebase not
  finished); a rebase that conflicts, a push the lease refuses, or a base that was rewritten or
  that no reflog records, leaves the branch as it was.
- For each of those, jbus tells the crew to move its own commits instead, under the key
  `restack|<slug>|<head 12>|<merge 12>`, from the commit its branch started from (`_started`):
  the newest head of the base that the link holds, of the base's last head, the heads the reflogs
  record, and the commit jbus cut the link's branch at, which its launch record keeps since the
  base's branch, and its reflog with it, is gone once the base merged. Only once the link moved
  or that message went does the line say `Stacked on: <slug> <branch> at <merge>`, so a message
  held for a capped thread is sent on a later pass, and the crew hears of its stack once.
  `jmerge` then waits until the link's head holds that commit (`ready.STACKED_UNMOVED`), and
  merges it as any other.

A row still before its pull request, its crew at its desk proof or waiting on the review jbus
launches (`prereview`), is moved by `before_pull` once its base merged. It moves the line onto the
branch the base merged into, in the brief's head and on its Result's own `Stacked on:` line,
`Stacked on: <slug> <branch> at <merge>`. Then, once its Result says its pull request opens after
the review and its crew is not at work, it moves the link's own commits there with the same
`_carry` an open link gets, from the branch origin has (`_lift`), on every pass until the pushed
head holds the merge. A squash merge leaves the base's own commits under the link and none of them
on main, so without the move the diff `prereview` reads from the link's fork with main holds the
base's files, and its `Proved:` line would have to name the base's tests. The move is made rather
than read around (a diff from the base's last head) since the pull request the crew then opens
needs the same move before `jmerge` merges it (`ready.STACKED_UNMOVED`). It runs before
`prereview.launch` in the pass, so the reviewer reads the moved head; its `Checked:` line no
longer binds that head, so `prereview` tells the crew to prove it again. A link `_carry` leaves
as it was waits for a later pass; the crew's blocks read the same line, and `jmerge` waits until
the head holds the merge as for any link.

A base closed with no merge leaves its link waiting on `jmerge`'s line: GitHub closes a pull
request whose base branch is deleted, and what to do with the work is the home's."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from jbriefs import below
from jbriefs.home import thread_of
from jbus import END_TURN, launchtext, mirror, queue, rebase, review, verbs
from jbus.launches import records
from jbus.passes import Pass
from jbus.prereview import pushed
from jbus.t3 import Client
from jbus.watch import World, against, at_work, task_brief
from jmerge import stacked as stacks

EVENTS = {"restack": "quiet"}
KIND = "restack"
MOVED = (
    "jbus: {base} merged as {merge}, and your stacked pull request #{number} is now based on "
    "{onto}, so its block rebases onto origin/{onto}. "
    'In your own worktree, read "A link that moved" in the crew skill again, from the file, '
    "and run its block with {was} as `was`: the commit your branch started from, the newest "
    "head of {base} it holds. Only if the block prints `not found`, run it again with {branch}. "
    + END_TURN
)


def move(run: Pass, client: Client, world: World) -> None:
    """Base each stacked link whose base merged on the branch it merged into, or the one its
    brief names, and move it there, or tell its crew to."""
    sent = set(run.box.sent())
    for slug, pull in world.open.items():
        head = str(pull.get("headRefOid") or "")
        brief = task_brief(run, slug)
        stacked = stacks.of(brief)
        if not head or stacked is None or stacked.at or stacked.slug in world.open:
            continue
        merged = world.merged.get(stacked.slug)
        if not merged or not rebase.crew(run, slug):
            continue
        onto = _onto(run, brief, merged)
        if onto:
            _moved(run, client, world, slug, pull, stacked, merged, onto, sent)
        else:
            run.say(f"wait {slug}: GitHub did not say what {stacked.slug} merged into")


def before_pull(run: Pass, world: World) -> None:
    """Move the `Stacked on:` line of each row with a crew and no pull request yet, whose base
    merged, onto the branch the base merged into: see the module."""
    for slug in sorted(world.threads):
        brief = task_brief(run, slug)
        stacked = stacks.of(brief)
        if stacked is None or slug in world.open or slug in world.merged:
            continue
        merged = world.merged.get(stacked.slug) or {}
        if not (merged.get("mergeCommit") or {}).get("oid") or not rebase.crew(run, slug):
            continue
        merge = str(merged["mergeCommit"]["oid"])
        onto = stacked.branch if stacked.at else _onto(run, brief, merged)
        if not onto:
            run.say(f"wait {slug}: GitHub did not say what {stacked.slug} merged into")
            continue
        if not stacked.at:
            moved = replace(stacked, branch=onto, at=merge)
            if not _rewrite(run, slug, moved, was=stacked):
                continue
            line = f"{KIND} {slug}: moved its Stacked on: line onto {onto}, {stacked.slug} merged"
            run.find(slug, KIND, line, stacks.line(moved), key=f"before pull {merge[:12]}")
            run.say(line)
        _lift(run, world, slug, merged, merge, onto)


def _lift(
    run: Pass, world: World, slug: str, merged: dict[str, Any], merge: str, onto: str
) -> None:
    """Move the own commits of a link whose Result waits on its review before its pull request
    onto `onto`, where its pushed head does not hold the base's `merge` yet: see the module."""
    live = world.threads[slug]
    result = mirror.last_result(task_brief(run, slug))
    if len(live) != 1 or at_work(live) or world.awaits(live[0]) or not review.before_pull(result):
        return
    branch = below.line(result, "Branch:").split()[0]
    head, last = pushed(run, branch), str(merged.get("headRefOid") or "")
    if not head or not last:
        return
    base = str(merged.get("headRefName") or "")
    moved = _carry(run, slug, head, branch, 0, base, last, merge, onto)
    if moved and moved != head:
        line = (
            f"{KIND} {slug}: moved its own commits onto {onto} before its review, "
            f"{merged.get('headRefName') or 'its base'} merged ({head[:12]} to {moved[:12]})"
        )
        run.find(slug, KIND, line, key=f"before pull {head[:12]} {merge[:12]}")
        run.say(line)


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
    key = rebase.mark(KIND, slug, head, merge[:12])
    if not merge or key in sent:
        return
    if pull.get("baseRefName") not in (None, "", onto):
        asked = run.run("gh", "pr", "edit", str(number), "--base", onto)
        if asked.returncode:
            said = (asked.stderr or asked.stdout).strip().splitlines()
            why = said[-1] if said else f"gh exited {asked.returncode}"
            run.say(f"wait {slug}: #{number} could not be based on {onto}: {why}")
            return
    thread = thread_of(run.home, slug)
    if rebase.held(run, client, thread, slug, number, head, key, KIND):
        return
    last = str(merged.get("headRefOid") or "")
    branch = str(pull.get("headRefName") or slug)
    moved = ""
    if last:
        moved = _carry(run, slug, head, branch, number, stacked.branch, last, merge, onto)
    if moved:
        run.box.mark(key)
        line = (
            f"{KIND} {slug}: moved its own commits onto {onto} once {stacked.slug} merged "
            f"(#{number}, {head[:12]} to {moved[:12]})"
        )
        run.find(slug, KIND, line, key=f"{head[:12]} {merge[:12]}")
        run.say(line)
        _rewrite(run, slug, replace(stacked, branch=onto, at=merge))
        return
    was = _started(run, slug, stacked.branch, branch, head, onto, last) or last or stacked.branch
    message = (
        MOVED.replace("{base}", stacked.slug)
        .replace("{merge}", merge[:12])
        .replace("{number}", str(number))
        .replace("{onto}", onto)
        .replace("{branch}", stacked.branch)
        .replace("{was}", was)
    )
    ask = rebase.Ask(
        KIND,
        "told the crew",
        "told to move its stacked link",
        message,
        head[:12],
        no_thread="stacked link with no thread to tell",
        refused="T3 Code refused the message to move a stacked link",
    )
    if not rebase.post(run, client, world, number, f"{stacked.slug} merged", ask, merge[:12]):
        return
    line = f"{KIND} {slug}: told the crew {stacked.slug} merged (#{number}, {head[:12]})"
    run.find(slug, KIND, line, message, key=f"{head[:12]} {merge[:12]}")
    run.say(line)
    _rewrite(run, slug, replace(stacked, branch=onto, at=merge))


def _carry(
    run: Pass,
    slug: str,
    head: str,
    branch: str,
    number: int,
    base: str,
    last: str,
    merge: str,
    onto: str,
) -> str:
    """Move the link's own commits on `branch` at `head`, those above `last`, the head its `base`
    branch merged at, onto `origin/<onto>`, and push them over the head the pass read. `number` is
    its pull request's, or 0 before it has one. Return the head the branch is at now, or nothing
    when it was left as it was, with the reason said."""
    if review.reviewing(task_brief(run, slug)):
        return _left(run, slug, "a reviewer it launched has written no review yet")
    crew = _worktree(run, branch)
    busy = _busy(run, crew, head) if crew else ""
    if busy:
        return _left(run, slug, f"its worktree {busy}")
    run.run("git", "fetch", "-q", "origin", f"+refs/heads/{onto}:refs/remotes/origin/{onto}")
    if run.run("git", "cat-file", "-e", f"{head}^{{commit}}").returncode:
        ref = f"refs/pull/{number}/head" if number else f"refs/heads/{branch}"
        run.run("git", "fetch", "-q", "origin", ref)
    if run.run("git", "merge-base", "--is-ancestor", merge, f"origin/{onto}").returncode:
        return _left(run, slug, f"origin/{onto} does not hold {merge[:12]} here")
    if not run.run("git", "merge-base", "--is-ancestor", merge, head).returncode:
        return head
    if run.run("git", "merge-base", "--is-ancestor", last, head).returncode:
        fork = _fork(run, slug, base, branch, last, head, onto)
        if not fork:
            return _left(run, slug, f"its head does not hold {last[:12]} here")
        last = fork
    new = _replay(run, slug, head, last, onto)
    return _push(run, slug, branch, head, new, crew) if new else ""


def _replay(run: Pass, slug: str, head: str, last: str, onto: str) -> str:
    """Rebase the commits of `head` above `last` onto `origin/<onto>` in a scratch worktree of
    jbus's own, and return the new head, or nothing when they conflict, with the reason said."""
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
        return run.run("git", "-C", str(tree), "rev-parse", "HEAD").stdout.strip()
    finally:
        run.run("git", "worktree", "remove", "--force", str(tree))
        shutil.rmtree(scratch, ignore_errors=True)


def _push(run: Pass, slug: str, branch: str, head: str, new: str, crew: Path | None) -> str:
    """Push `new` over `branch` at `head`, the head the pass read, and move the crew's worktree
    to it. Return `new`, or nothing when the lease refused it, with the reason said."""
    run.run("git", "update-ref", f"refs/jstack/pre-rebase/{slug}/{head[:12]}", head)
    lease = f"--force-with-lease=refs/heads/{branch}:{head}"
    if run.run("git", "push", "-q", lease, "origin", f"{new}:refs/heads/{branch}").returncode:
        why = f"origin's {branch} is no longer at {head[:12]}, or did not answer"
        return _left(run, slug, why)
    if crew and run.run("git", "-C", str(crew), "reset", "-q", "--keep", new).returncode:
        run.say(f"wait {slug}: its worktree {crew} could not follow the move to {new[:12]}")
    return new


def _fork(run: Pass, slug: str, base: str, branch: str, last: str, head: str, onto: str) -> str:
    """Where the link `slug` on `branch` left its `base` branch, when the base only grew after the
    link was stacked on it: the fork of the base's `last` head and the link's `head`. The base only
    grew when one of the heads it had (`_heads`) is under the link's head and every one under it
    is under `last` too. Nothing when the base dropped a head the link holds, as an amend or a
    rebase does, or when no record is left to say."""
    under = [one for one in _heads(run, slug, base, branch, onto) if _holds(run, head, one)]
    if not under or not all(_holds(run, last, one) for one in under):
        return ""
    return run.run("git", "merge-base", last, head).stdout.strip()


def _started(run: Pass, slug: str, base: str, branch: str, head: str, onto: str, last: str) -> str:
    """The commit the link `slug` on `branch` at `head` started from: the newest head its `base`
    had that the link holds, of the base's `last` head and those `_heads` reads. Nothing when the
    link holds none, or two that neither holds."""
    known = {last} if last else set()
    known |= _heads(run, slug, base, branch, onto)
    under = [one for one in known if _holds(run, head, one)]
    newest = [one for one in under if all(_holds(run, one, other) for other in under)]
    return newest[0] if newest else ""


def _heads(run: Pass, slug: str, base: str, branch: str, onto: str) -> set[str]:
    """The heads the link `slug`'s `base` branch had, from this machine's record of them: the
    reflogs of its local and remote-tracking branch, which are gone once the base's branch is
    deleted, the commit jbus cut the link's own `branch` at, kept in its launch records, and the
    oldest entry of that branch's reflog, the base's head it was made at. A commit `origin/<onto>`
    holds is no head of the base: a launch or a branch made there."""
    heads: set[str] = set()
    for ref in (f"refs/heads/{base}", f"refs/remotes/origin/{base}"):
        said = run.run("git", "reflog", "show", "--format=%H", ref, "--")
        heads.update(said.stdout.split() if not said.returncode else ())
    said = run.run("git", "reflog", "show", "--format=%H", f"refs/heads/{branch}", "--")
    made = said.stdout.split()[-1:] if not said.returncode else []
    made += [str(one.get("sha") or "") for _, one in records(run, slug, queue.CREW)]
    heads.update(one for one in made if one and not _holds(run, f"origin/{onto}", one))
    return heads


def _holds(run: Pass, head: str, commit: str) -> bool:
    return not run.run("git", "merge-base", "--is-ancestor", commit, head).returncode


def _left(run: Pass, slug: str, why: str) -> str:
    run.say(f"{KIND} {slug}: jbus left its branch as it was ({why}), so its crew moves it")
    return ""


def _worktree(run: Pass, branch: str) -> Path | None:
    """The worktree that has the branch checked out, the crew's, or None."""
    listed = run.run("git", "worktree", "list", "--porcelain").stdout
    for entry in listed.split("\n\n"):
        fields = {
            key: value for key, _, value in (line.partition(" ") for line in entry.splitlines())
        }
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


def _rewrite(
    run: Pass, slug: str, stacked: stacks.Stacked, was: stacks.Stacked | None = None
) -> bool:
    """Write where the link sits now on its brief's `Stacked on:` line, read again just before,
    so a line its crew added since is kept. Given the line it `was`, a Result's own `Stacked on:`
    line of that stack is moved too, with what followed the branch on it, the base's url. Return
    whether it was written."""
    path = run.home / "tasks" / f"{slug}.md"
    try:
        text = launchtext.stacked(path.read_text(errors="replace"), stacked)
        if was is not None:
            old = f"{stacks.LINE} {was.slug} {was.branch}".split()
            head, mark, body = text.partition("\n## ")
            text = (
                head
                + mark
                + "".join(
                    " ".join([stacks.line(stacked), *line.split()[4:]]) + "\n"
                    if line.split()[:4] == old
                    else line
                    for line in body.splitlines(keepends=True)
                )
            )
        path.write_text(text)
    except OSError as error:
        run.say(f"wait {slug}: its Stacked on: line could not be written ({error})")
        return False
    return True


STEPS = (
    verbs.Step(
        "tellers",
        34,
        "stack.before_pull",
        lambda half: before_pull(half.run, half.seen.world),
        ("world",),
    ),
    verbs.Step(
        "after-expedite",
        27,
        "stack.move",
        lambda half: move(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
