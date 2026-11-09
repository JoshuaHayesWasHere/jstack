"""Launch a brief's reviewers once its crew's desk proof is on record at the head it pushed, and
tell the crew when every reviewer has written, so that its pull request opens after its review.

The order is: the brief, the crew's work and its desk proof (the `Checked:` and `Proved:` lines of
the crew skill's check and proof blocks), the review, the pull request, the merge. The review
reads a head the desk proof passed, so it runs while nothing else does, and CI's check runs once,
on the pull request that follows the review.

A crew whose desk proof passed pushes its branch and writes its Result with `Branch: <branch>
Pull request: after the review` (`review.AFTER`), then ends its turn. `launch` reads each such row
on each pass: its crew's thread is not at work, it has no pull request, its brief asks for a review
and has no reviewer yet. It asks origin for the branch's head, and `jmerge`'s own rules whether the
brief's last `Checked:` line and its `Proved:` line bind that head (`ready.short_on_checked`,
`ready.short_on_proved`, over the files the branch changes since its base). Where they do, it
launches one reviewer for each line of the role map's review list (`jroles.pool.routes`), each a
thread titled `review: <slug>, <n>` in the crew's worktree, told `/pr-review run <slug> <n>`, and
adds a `Reviewer: <thread> #<n>` line for each under the Result, the line every reader of the
roster parses. Where they do not, or origin has no such branch, or T3 Code names no worktree for
the crew, the row is a condition, once for its head: the crew wrote that it waits on a review it
has not earned. jbus also tells the crew, once for that head (the one origin has, else the
branch's own), under `prereview-refused|<slug>|<head 12>` (`refuse`): what does not hold, and that
it fixes it, pushes and writes a follow-up Result that still opens its pull request after the
review. The message is sent here and not by `threads.resume`, which sends nothing to a crew whose
review is awaited: only this pass knows the head it read and why it refused it. Meanwhile the row
runs, waiting on its review (`watch.owes_pull`), whatever its Result's `Left:` line names, and
the crew's follow-up Result is read like the first.

The key `reviewers|<slug>|<head 12>` is marked before the first launch, since a launch has no
retry key: a pass that crashes after it launches no reviewer twice. A pass that finds every
instance of the review pool capped launches nothing and marks nothing, and the next pass asks
again.

`tell` reads the same rows once each reviewer jbus launched has written a `## Review` that ran
(`review.ran`), and sends the crew one message under `prereviewed|<slug>|<head 12>`, the
head the sections reviewed: the review is in, with its findings by id, so the crew handles them
and opens the pull request. It also marks the key of `threads.resume`'s own message that a Result
owes its pull request (`owes-pull|<slug>|<thread>`), which this message takes the place of. Until
then `threads.resume` and `watch` read the row as waiting on jbus (`review.awaited`).
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import jroles
from jbriefs import below, findings
from jbus import END_TURN, dispatch, mirror, outbox, rebase, review, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, _default_branch, at_work, task_brief
from jmerge import ready
from jroles import pool

EVENTS = {"prereview": "quiet", "prereviewed": "quiet", "prereview-refused": "quiet"}
TITLE = "review: {slug}, {n}"
ASK = "/pr-review run {slug} {n}"
UNPROVED = "its Result waits on a review, and its desk proof does not hold at its pushed head"
UNPUSHED = "its Result waits on a review, and origin has no branch {branch}"
NO_TREE = "its Result waits on a review, and T3 Code names no worktree for its crew"
LOST = "a reviewer's launch got no reply"
TEMPLATE = "prereviewed"
REFUSED = "prereview-refused"
REFUSAL = (
    "jbus: {slug}'s review was not launched: {why}.{detail}\n\n"
    "Fix that in your worktree, push the branch, and write a follow-up Result in the same shape "
    "that still says `Pull request: after the review`, with the `Checked:` and `Proved:` lines "
    "of the head you pushed. jbus launches the review once they hold there. " + END_TURN
)
TAIL = 2000
"""How many of `outbox.jsonl`'s last lines `told_at` reads."""
MESSAGE = (
    "jbus: {slug}'s review at {head} is written, before its pull request, in the brief's "
    '`## Review` {sections}. Handle its findings as the crew skill\'s "The review" says, then '
    'open the pull request as "Do the task" says, and write a follow-up Result that names it, '
    "with the `Finding` and `Fixed:` lines.\n\n"
    "The findings of that review, by id (`jbriefs --findings` on the brief lists every one):\n"
    "{found}\n\n" + END_TURN
)


def _rows(run: Pass, world: World) -> list[tuple[str, dict[str, Any], str, str]]:
    """Each row whose crew waits on the review before its pull request: its slug, its one crew
    thread, which is not at work, its brief and its last Result."""
    found = []
    for slug, live in sorted(world.threads.items()):
        if len(live) != 1 or at_work(live) or slug in world.open or slug in world.merged:
            continue
        if slug in run.gated:
            continue
        brief = task_brief(run, slug)
        result = mirror.last_result(brief)
        if review.before_pull(result) and findings.mode_of(brief) != findings.NONE:
            found.append((slug, live[0], brief, result))
    return found


def pushed(run: Pass, branch: str) -> str:
    """The head origin has for `branch`, or nothing where it has no such branch."""
    said = run.run("git", "ls-remote", "origin", f"refs/heads/{branch}")
    words = said.stdout.split() if said.returncode == 0 else []
    return words[0] if words else ""


def changes(run: Pass, brief: str, head: str) -> ready.PullRequest:
    """The pull request the branch at `head` would open, as far as `ready.short_on_proved` reads
    one: the files it changes since it left its base, and those it deletes. The base is the branch
    of the brief's `Stacked on:` line, else the default branch, as the crew's blocks read it."""
    stacked = below.line(brief.split("\n## ")[0], "Stacked on:")
    on = stacked.split()[1] if len(stacked.split()) > 1 else _default_branch(run)
    base = run.run("git", "merge-base", f"origin/{on}", head).stdout.strip()
    listed = run.run("git", "diff", "--name-status", "--no-renames", base, head).stdout
    status = [line.split("\t", 1) for line in listed.splitlines() if "\t" in line]
    files = tuple(path for _, path in status)
    removed = tuple(path for kind, path in status if kind.startswith("D"))
    return ready.PullRequest(
        number=0,
        url="",
        title="",
        branch="",
        head=head,
        base=on,
        mergeable="",
        waiting=(),
        files=files,
        renamed=False,
        changed=len(files),
        removed=removed,
    )


def proved(run: Pass, brief: str, head: str) -> str:
    """Why the brief's desk proof does not bind `head`, or nothing: `jmerge`'s rules of the
    `Checked:` and `Proved:` lines, with no other head carried."""
    return ready.short_on_checked(brief, head) or ready.short_on_proved(
        brief, changes(run, brief, head)
    )


def arguments(
    run: Pass, slug: str, n: int, tree: str, branch: str, routed: pool.Route | None
) -> dict[str, Any]:
    """The arguments of `t3_thread_launch` for reviewer `n`: in the crew's worktree, on its
    branch, as the crew skill's launch block makes them."""
    made: dict[str, Any] = {
        "projectId": run.project.project_id,
        "title": TITLE.format(slug=slug, n=n),
        "workspaceStrategy": {"type": "existing_worktree", "worktreePath": tree, "branch": branch},
        "message": ASK.format(slug=slug, n=n),
    }
    if run.config.runtime_mode:
        made["runtimeMode"] = run.config.runtime_mode
    if routed is not None:
        made["modelSelection"] = routed.as_json()
    return made


def _record(run: Pass, slug: str, lines: list[str]) -> None:
    """Add the `Reviewer:` lines under the Result, to the brief as it is now."""
    path = run.home / "tasks" / f"{slug}.md"
    text = path.read_text(errors="replace")
    path.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(lines))


def launch(run: Pass, client: Client, world: World) -> None:
    """Launch the reviewers of each row whose desk proof holds at its pushed head: see the
    module."""
    sent = run.box.sent()
    for slug, thread, brief, result in _rows(run, world):
        if review.launched(brief) or review.reviewed(brief):
            continue
        branch = below.line(result, "Branch:").split()[0]
        head = pushed(run, branch)
        if not head:
            why = UNPUSHED.format(branch=branch)
            run.condition(slug, why, key=f"unpushed {branch}")
            local = run.run("git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}^{{commit}}")
            refuse(run, client, slug, thread, local.stdout.strip() or branch, why, "", sent)
            continue
        key = f"reviewers|{slug}|{head[:12]}"
        if key in sent:
            continue
        short = proved(run, brief, head)
        if short:
            run.condition(slug, UNPROVED, f"at {head}: {short}", key=f"unproved {head[:12]}")
            refuse(run, client, slug, thread, head, UNPROVED, f"at {head}: {short}", sent)
            continue
        tree = rebase.worktree(client, thread["threadId"])
        if not tree:
            run.condition(slug, NO_TREE, thread["threadId"], key=f"no tree {head[:12]}")
            refuse(run, client, slug, thread, head, NO_TREE, "", sent)
            continue
        try:
            out = dispatch.cannot_sign_in(run, client)
            routes: list[pool.Route | None] = list(pool.routes("review", run.now, out))
        except jroles.Refused as error:
            run.say(f"note {slug}: the role map gives the review no model ({error}): it inherits")
            routes = []
        capped = [one.choice.why for one in routes if one and one.choice.instance is None]
        if capped:
            run.say(f"wait {slug}: no reviewer launched: {'; '.join(capped)}")
            continue
        run.box.mark(key)
        lines = []
        for n, routed in enumerate(routes or [None], start=1):
            asked = arguments(run, slug, n, tree, branch, routed)
            try:
                made, why = (client.call("t3_thread_launch", asked) or {}).get("threadId"), ""
            except (T3Refused, T3Error) as error:
                made, why = None, f": {error}"
            if not made:
                run.condition(slug, LOST, f"reviewer #{n} at {head}{why}", key=f"lost {key}")
                break
            lines.append(f"Reviewer: {made} #{n}\n")
        if lines:
            _record(run, slug, lines)
            named = ", ".join(line.split()[1] for line in lines)
            said = f"launched review {slug}: {named} at {head[:12]}"
            run.find(slug, "prereview", said, "".join(lines), key=head[:12])
            run.say(said)


def refuse(
    run: Pass,
    client: Client,
    slug: str,
    thread: dict[str, Any],
    head: str,
    why: str,
    detail: str,
    sent: list[str],
) -> None:
    """Tell the crew, once for `head`, why jbus launched no review of its Result: see the
    module. `head` is the head origin has, or the branch's own where it has none."""
    key = f"{REFUSED}|{slug}|{head[:12]}"
    if key in sent:
        return
    at = thread["threadId"]
    text = REFUSAL.format(slug=slug, why=why, detail=f"\n\n{detail}" if detail else "")
    try:
        went = outbox.send(
            run, client, thread=at, row=slug, key=key, text=text, template=REFUSED, needs="act"
        )
    except T3Refused as error:
        what = "T3 Code refused the message that its review was not launched"
        run.gate(slug, what, f"{error}\n\n{text}", key=key)
        return
    except T3Error as error:
        run.say(f"wait {slug}: why its review was not launched could not be sent ({error})")
        return
    if not went:
        return
    run.box.mark(key)
    line = f"{REFUSED} {slug}: told {at} why its review at {head[:12]} was not launched"
    run.find(slug, REFUSED, line, text, key=head[:12])
    run.say(line)


def due(brief: str) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    """The head the review jbus launched saw, the `By:` lines of its sections and its findings
    by id, once every reviewer jbus launched has written a section that ran, as `jbus.reviewed`
    reads them; None before then. A `Verdict: not run` section is no review: the row still
    waits (`review.awaited`), and the clock asks its reviewer again."""
    if not review.launched(brief) or review.launched(brief) > review.ran(brief):
        return None
    triage = findings.triage(brief)
    ran = [one for one in triage.sections if one.ran and one.head]
    head = ran[-1].head
    by = tuple(dict.fromkeys(one.by for one in ran if one.head == head and one.by))
    return head, by, tuple(findings.listed(triage))


def told_at(state: Path, slug: str) -> datetime | None:
    """When jbus last sent the slug's crew `prereviewed`, as the tail of `outbox.jsonl` has it, or
    None where it has no such send."""
    try:
        with open(state / outbox.FILE) as file:
            tail = deque(file, maxlen=TAIL)
    except OSError:
        return None
    at = None
    for line in tail:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if one.get("template") == TEMPLATE and one.get("row") == slug and one.get("went") == "sent":
            at = datetime.fromisoformat(one["at"])
    return at


def tell(run: Pass, client: Client, world: World) -> None:
    """Tell each crew whose review before its pull request is all written, once for its head."""
    sent = run.box.sent()
    for slug, thread, brief, _ in _rows(run, world):
        said = due(brief)
        if said is None:
            continue
        head, by, found = said
        key = f"prereviewed|{slug}|{head[:12]}"
        if key in sent:
            continue
        at = thread["threadId"]
        text = MESSAGE.format(
            slug=slug,
            head=head[:12],
            sections="; ".join(f"`By: {one}`" for one in by) or "with no `By:` line",
            found="\n".join(found) or "none: the review is clean",
        )
        try:
            went = outbox.send(
                run, client, thread=at, row=slug, key=key, text=text, template=TEMPLATE, needs="act"
            )
        except T3Refused as error:
            run.gate(slug, "T3 Code refused the review's message", f"{error}\n\n{text}", key=key)
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its review's message could not be sent ({error})")
            continue
        if not went:
            continue
        run.box.mark(key)
        run.box.mark(f"owes-pull|{slug}|{at}")
        line = f"prereviewed {slug}: told {at} of its review at {head[:12]}"
        run.find(slug, "prereviewed", line, text, key=head[:12])
        run.say(line)


def _launch(half: Any) -> None:
    launch(half.run, half.client, half.seen.world)


def _tell(half: Any) -> None:
    tell(half.run, half.client, half.seen.world)


STEPS = (
    verbs.Step("tellers", 35, "prereview.launch", _launch, ("client", "world")),
    verbs.Step("tellers", 57, "prereview.tell", _tell, ("client", "world")),
)
