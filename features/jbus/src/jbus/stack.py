"""This module takes a stacked link off its stack where it has no need of its base's code, and
moves a stacked link onto the branch its base merged into, or tells its crew to.

A row whose brief builds on another row's code (`--depends`, named on its `Builds on:` line)
launches once that row has opened its pull request, stacked on that pull request's branch
(`dispatch`, `World.stack_on`). Its brief's `Stacked on: <slug> <branch>` line is the one record
of the stack: the crew opens its pull request on that branch, and `jmerge` waits on the line
(`ready.STACKED_ON`).

While the base is open, a link whose pull request is open comes off the stack when its own change
has no need of the base's (`unstack`): its own commits merge cleanly onto the branch the base goes
on without the base's, and its added lines use no `def`, `class` or top-level constant the base
introduced. These are the replay's two tests (`reports/merge-velocity/stack_need.py`), checked
once for each head of the link and of its base. jbus moves those commits onto that branch, bases
the pull request there and drops the brief's `Stacked on:` line, under the same holds as a move
below, so `jmerge` no longer waits on the base and the link merges on its own. A link that
conflicts without its base, or uses such a name, stays stacked, and so does a link whose base is
itself still stacked. A `merge_after` order is the home's word on merging and is kept as it is.

Otherwise its link's crew is told nothing while the base is open, whatever the base's head does:
the link is moved once, when the base merged. Each pass reads every open pull request whose brief
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
  base that this machine's reflogs record under the link's head is under the base's last head.
  jbus moves nothing while the outbox holds the crew (`rebase.held`): its thread is at work, waits
  on a test slot, or waits on a review it launched that jmerge says is not written at the head.
  Such a link waits for a later pass, and its crew is told nothing. Nor does jbus move it while a
  reviewer the crew launched has written no review (`review.reviewing`), since a move would change
  the head under it, or while its worktree has work in it (uncommitted, unpushed or a rebase not
  finished); a rebase that conflicts, a push the lease refuses, or a base that was rewritten or
  that no reflog records, leaves the branch as it was.
- For each of those, jbus tells the crew to move its own commits instead, from the base's last
  head, under the key `restack|<slug>|<head 12>|<merge 12>`. Only once the link moved or that
  message went does the line say `Stacked on: <slug> <branch> at <merge>`, so a message held for a
  capped thread is sent on a later pass, and the crew hears of its stack once. `jmerge` then waits
  until the link's head holds that commit (`ready.STACKED_UNMOVED`), and merges it as any other.

A base closed with no merge leaves its link waiting on `jmerge`'s line: GitHub closes a pull
request whose base branch is deleted, and what to do with the work is the home's."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from jbriefs.home import thread_of
from jbus import END_TURN, dispatch, rebase, review, verbs
from jbus.passes import Pass
from jbus.t3 import Client
from jbus.watch import World, against, task_brief
from jmerge import stacked as stacks

EVENTS = {"restack": "quiet", "unstack": "quiet"}
KIND = "restack"
UNSTACK = "unstack"
MOVED = (
    "jbus: {base} merged as {merge}, and your stacked pull request #{number} is now based on "
    "{onto}, so its block rebases onto origin/{onto}. "
    'In your own worktree, read "A link that moved" in the crew skill again, from the file, '
    "and run its block with {was} as the branch it sat on. That commit is the head {base} merged "
    "at. If the block prints `not found`, run it again with {branch}. " + END_TURN
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
    moved = _carry(run, slug, pull, stacked.branch, last, merge, onto) if last else ""
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
    last = last or stacked.branch
    message = (
        MOVED.replace("{base}", stacked.slug)
        .replace("{merge}", merge[:12])
        .replace("{onto}", onto)
        .replace("{branch}", stacked.branch)
        .replace("{was}", last)
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
    run: Pass, slug: str, pull: dict[str, Any], base: str, last: str, merge: str, onto: str
) -> str:
    """Move the link's own commits, those above `last`, the head its `base` branch merged at, onto
    `origin/<onto>`, and push them over the head the pass read. Return the head the branch is at
    now, or nothing when it was left as it was, with the reason said."""
    head, number = str(pull["headRefOid"]), pull["number"]
    branch = str(pull.get("headRefName") or slug)
    if review.reviewing(task_brief(run, slug)):
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
        fork = _fork(run, base, last, head)
        if not fork:
            return _left(run, slug, f"its head does not hold {last[:12]} here")
        last = fork
    new = _replay(run, slug, head, last, onto)
    return _push(run, slug, branch, head, new, crew) if new else ""


def _replay(run: Pass, slug: str, head: str, last: str, onto: str, kind: str = KIND) -> str:
    """Rebase the commits of `head` above `last` onto `origin/<onto>` in a scratch worktree of
    jbus's own, and return the new head, or nothing when they conflict, with the reason said."""
    scratch = Path(tempfile.mkdtemp(prefix=f"jbus-move-{slug}-"))
    tree = scratch / "tree"
    try:
        made = run.run("git", "worktree", "add", "-q", "--detach", str(tree), head)
        if made.returncode:
            return _left(run, slug, "jbus's scratch worktree could not be made", kind)
        moved = run.run("git", "-C", str(tree), "rebase", "-q", "--onto", f"origin/{onto}", last)
        if moved.returncode:
            run.run("git", "-C", str(tree), "rebase", "--abort")
            return _left(run, slug, f"its commits conflict with origin/{onto}", kind)
        return run.run("git", "-C", str(tree), "rev-parse", "HEAD").stdout.strip()
    finally:
        run.run("git", "worktree", "remove", "--force", str(tree))
        shutil.rmtree(scratch, ignore_errors=True)


def _push(
    run: Pass, slug: str, branch: str, head: str, new: str, crew: Path | None, kind: str = KIND
) -> str:
    """Push `new` over `branch` at `head`, the head the pass read, and move the crew's worktree
    to it. Return `new`, or nothing when the lease refused it, with the reason said."""
    run.run("git", "update-ref", f"refs/jstack/pre-rebase/{slug}/{head[:12]}", head)
    lease = f"--force-with-lease=refs/heads/{branch}:{head}"
    if run.run("git", "push", "-q", lease, "origin", f"{new}:refs/heads/{branch}").returncode:
        why = f"origin's {branch} is no longer at {head[:12]}, or did not answer"
        return _left(run, slug, why, kind)
    if crew and run.run("git", "-C", str(crew), "reset", "-q", "--keep", new).returncode:
        run.say(f"wait {slug}: its worktree {crew} could not follow the move to {new[:12]}")
    return new


def _fork(run: Pass, base: str, last: str, head: str) -> str:
    """Where the link left its `base` branch, when the base only grew after the link was stacked
    on it: the fork of the base's `last` head and the link's `head`. The heads the base had are
    read from this machine's record of them, the reflogs of its local and remote-tracking branch,
    and the base only grew when one of them is under the link's head and every one under it is
    under `last` too. Nothing when the base dropped a head the link holds, as an amend or a rebase
    does, or when no record is left to say."""
    heads: set[str] = set()
    for ref in (f"refs/heads/{base}", f"refs/remotes/origin/{base}"):
        said = run.run("git", "reflog", "show", "--format=%H", ref, "--")
        heads.update(said.stdout.split() if not said.returncode else ())
    under = [one for one in heads if _holds(run, head, one)]
    if not under or not all(_holds(run, last, one) for one in under):
        return ""
    return run.run("git", "merge-base", last, head).stdout.strip()


def _holds(run: Pass, head: str, commit: str) -> bool:
    return not run.run("git", "merge-base", "--is-ancestor", commit, head).returncode


def _left(run: Pass, slug: str, why: str, kind: str = KIND) -> str:
    then = "so its crew moves it" if kind == KIND else "so it stays stacked for now"
    run.say(f"{kind} {slug}: jbus left its branch as it was ({why}), {then}")
    return ""


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


def _rewrite(run: Pass, slug: str, stacked: stacks.Stacked | None) -> None:
    """Write where the link sits now on its brief's `Stacked on:` line, read again just before,
    so a line its crew added since is kept, or drop the line once it sits on no stack."""
    path = run.home / "tasks" / f"{slug}.md"
    try:
        text = path.read_text(errors="replace")
        path.write_text(dispatch.stacked(text, stacked))
    except OSError as error:
        run.say(f"wait {slug}: its Stacked on: line could not be written ({error})")


def unstack(run: Pass, client: Client, world: World) -> None:
    """Take each stacked link whose base is still open off its stack where its own change has no
    need of the base's: its own commits merge cleanly onto the branch the base goes on without the
    base's, and its added lines use no name the base introduced (`need`)."""
    sent = set(run.box.sent())
    for slug, pull in world.open.items():
        head = str(pull.get("headRefOid") or "")
        brief = task_brief(run, slug)
        stacked = stacks.of(brief)
        base = world.open.get(stacked.slug) if stacked and not stacked.at else None
        if not head or stacked is None or base is None or not rebase.crew(run, slug):
            continue
        last, onto = str(base.get("headRefOid") or ""), str(base.get("baseRefName") or "")
        if not last or not onto or stacks.unmoved(task_brief(run, stacked.slug)):
            continue
        key = rebase.mark(UNSTACK, slug, head, last[:12])
        if key not in sent:
            _unstack(run, client, slug, pull, stacked, base, onto, key)


def _unstack(
    run: Pass,
    client: Client,
    slug: str,
    pull: dict[str, Any],
    stacked: stacks.Stacked,
    base: dict[str, Any],
    onto: str,
    key: str,
) -> None:
    head, number = str(pull["headRefOid"]), pull["number"]
    last = str(base["headRefOid"])
    fork = _own(run, slug, pull, base, onto)
    if not fork:
        return
    start = run.run("git", "merge-base", f"origin/{onto}", last).stdout.strip()
    if not start:
        return
    needed = need(lambda *args: run.run("git", *args), fork, head, f"origin/{onto}", start, last)
    if needed:
        run.box.mark(key)
        run.say(f"{UNSTACK} {slug}: stays stacked on {stacked.slug}, since {needed}")
        return
    if review.reviewing(task_brief(run, slug)):
        _left(run, slug, "a reviewer it launched has written no review yet", UNSTACK)
        return
    branch = str(pull.get("headRefName") or slug)
    crew = _worktree(run, branch)
    busy = _busy(run, crew, head) if crew else ""
    if busy:
        _left(run, slug, f"its worktree {busy}", UNSTACK)
        return
    if rebase.held(run, client, thread_of(run.home, slug), slug, number, head, key, UNSTACK):
        return
    new = _replay(run, slug, head, fork, onto, UNSTACK)
    if not new:
        return
    if pull.get("baseRefName") not in (None, "", onto):
        asked = run.run("gh", "pr", "edit", str(number), "--base", onto)
        if asked.returncode:
            said = (asked.stderr or asked.stdout).strip().splitlines()
            why = said[-1] if said else f"gh exited {asked.returncode}"
            run.say(f"wait {slug}: #{number} could not be based on {onto}: {why}")
            return
    if not _push(run, slug, branch, head, new, crew, UNSTACK):
        return
    run.box.mark(key)
    line = (
        f"{UNSTACK} {slug}: off its stack on {stacked.slug}, since its own commits merge onto "
        f"{onto} without it and use no name it introduced (#{number}, {head[:12]} to {new[:12]})"
    )
    run.find(slug, UNSTACK, line, key=f"{head[:12]} {last[:12]}")
    run.say(line)
    _rewrite(run, slug, None)


def _own(run: Pass, slug: str, pull: dict[str, Any], base: dict[str, Any], onto: str) -> str:
    """Where the link's own commits start: its base's head, or the fork of the two where the base
    took commits after the link was stacked on it (`_fork`). Nothing when a commit cannot be read
    here or the base was rewritten under it, with the reason said."""
    head, last = str(pull["headRefOid"]), str(base["headRefOid"])
    run.run("git", "fetch", "-q", "origin", f"+refs/heads/{onto}:refs/remotes/origin/{onto}")
    for one in (pull, base):
        commit, branch = str(one["headRefOid"]), str(one.get("headRefName") or "")
        if run.run("git", "cat-file", "-e", f"{commit}^{{commit}}").returncode and branch:
            run.run(
                "git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
            )
        if run.run("git", "cat-file", "-e", f"{commit}^{{commit}}").returncode:
            run.run("git", "fetch", "-q", "origin", f"refs/pull/{one['number']}/head")
        if run.run("git", "cat-file", "-e", f"{commit}^{{commit}}").returncode:
            return _left(run, slug, f"{commit[:12]} cannot be read here", UNSTACK)
    if _holds(run, head, last):
        return last
    fork = _fork(run, str(base.get("headRefName") or ""), last, head)
    return fork or _left(run, slug, f"its base was rewritten under {head[:12]}", UNSTACK)


_NAMED = (
    re.compile(r"\+\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w{3,})"),
    re.compile(r"\+([A-Z_][A-Z0-9_]{3,})\s*[:=]"),
)


def need(
    git: Callable[..., subprocess.CompletedProcess[str]],
    fork: str,
    head: str,
    onto: str,
    start: str,
    last: str,
) -> str:
    """What of its base the link's own change, `fork` to `head`, needs, or nothing. These are the
    two tests of the replay that measured stacks (`reports/merge-velocity/stack_need.py`, which
    calls this): the change conflicts with `onto` without the base's commits, or its added lines
    use a `def`, a `class` or a top-level constant that the base's change, `start` to `last`, adds
    and no file of `onto` has. `git` runs a git command in the repository and returns what it
    did."""
    merged = git("merge-tree", "--write-tree", "--no-messages", f"--merge-base={fork}", onto, head)
    if merged.returncode == 1:
        return f"its own commits conflict with {onto} without it"
    if merged.returncode:
        return f"git could not merge its own commits onto {onto}"
    names = {
        found[1]
        for line in git("diff", start, last).stdout.splitlines()
        for pattern in _NAMED
        if (found := pattern.match(line))
    }
    added = "\n".join(
        line for line in git("diff", fork, head).stdout.splitlines() if line.startswith("+")
    )
    used = sorted(
        name
        for name in names
        if re.search(rf"\b{re.escape(name)}\b", added)
        and git("grep", "-q", "-w", name, onto).returncode == 1
    )
    return f"it uses {', '.join(used[:5])}, which its base introduced" if used else ""


STEPS = (
    verbs.Step(
        "after-expedite",
        26,
        "stack.unstack",
        lambda half: unstack(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
    verbs.Step(
        "after-expedite",
        27,
        "stack.move",
        lambda half: move(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
