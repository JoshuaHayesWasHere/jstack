"""This module tells a crew to rebase. A launch no longer holds back a brief that shares a file with
another brief, and this message is the safety that replaces that hold.

No row waits for another brief's files, so two crews may change the same file, each in its own
worktree. The merge decides which change goes in. `jmerge` waits on a pull request when the default
branch moved under the pull request or when the pull request conflicts with its base. `jmerge` says
so on a `wait` line. `tell` reads those lines and sends the crew one message for each head. The
message names a backup ref for the head that the rebase rewrites, and a lease that names that head.
With the backup ref and the lease, a rebase never loses what was on the branch.
jbus alone merges, so no home waits on a crew's line on green after a fix (`owed`).

The key of the message is `rebase|<slug>|<head 12>`. T3 Code uses the key to retry, and jbus writes
the key in `sent.json` as a mark of the send. So a pass that got no answer tries again, and jbus
never tells the same head twice. For main moving or for a failure, jbus tells a pull request to
rebase only once. A crew may rebase and then find its pull request stale or failing again at a new
head. jbus then parks a gate (`SECOND`) with the default that the pull request waits, and asks for
no second rebase. jbus tells of a conflict with the base at every head, since nothing but a rebase
resolves a conflict.

`tell` also reads a second kind of `wait` line, about a rebase that changed what the patch says.
`jmerge` keeps a review valid across a rebase whose range-diff changes no content, and waits on a
rebase whose range-diff changes content. jbus then asks the crew for one scoped review of that
range-diff, under the key `rereview|<slug>|<head 12>`. jbus asks once for each head, so it never
asks for a second review of the same head.

The third kind of `wait` line is about a rebase that dropped lines nobody explained. `jmerge` waits
on such a rebase, and jbus tells the crew once per head, under the key `drops|<slug>|<head 12>`. The
crew puts the lines back, or says for each file why the lines are gone. `jmerge` then waits on the
scoped review that rules on those reasons, and its line names the range-diff, as the changed-content
line does. So the third kind ends in a scoped-review ask too: jbus asks the crew for that review
once per head, under `rereview|<slug>|<head 12>`. A head that already has that mark, or whose
Result has a `Scoped reviewer:` line of it, is asked nothing more.

`deliver` is the one function that sends these messages. `post` sends the message without writing
the event, and `expedite` calls `post` and writes an event of its own.

Each of these messages names a head. jbus sends each message with `mode: queue`, so the crew reads
the message in a separate turn, after its running turn ends. In two cases the crew would read the
message after the head that it names is gone: the crew's thread is at work, or the pull request has
moved to a new head since the pass listed it. In both cases `held` delays the message to a later
pass. A pass sends other messages first, so `held` asks T3 Code and GitHub again just before the
send. A thread that got one of these messages earlier in the same pass counts as at work, so a pass
sends a thread at most one of them. jbus writes no mark for a message that it delayed, so the next
pass decides again, using the head and the reasons as they are then.

`mainmoved` calls `held` too. Between them, the two modules tell a crew to rebase a given head only
once. The first of the two to tell the head also writes the key of the other. When this module sends
the rebase message, `post` writes the `mainmoved` key for the commit that main points to. When
`mainmoved` tells a head, it writes this module's key for that head.

T3 Code has no watch that wakes a crew. Instead, `github` calls `deliver` to send the crew a message
for each thing on GitHub that needs the crew to act. There are three such things.

The first is a check that ran and failed at a head, under `failed|<slug>|<head 12>`, with the
failure told beside it: GitHub's merge of main onto a head told of the same failure is not told
again, a crew push or another failure is (`told_before`). A rerun red again is told once more, under
`refailed|<slug>|<head 12>`. A check that ran no step is not told: no push repairs it.
When the crew already got the rebase message for a head, `github` sends no message for the head's
failed check, since a rebase is the fix that the failed check needs.

The second is a conflict with the base at a head, of a pull request that is not a stacked link
still on its base's branch (`stack` tells that one when to move). Before the reviewer writes the
review, `github` sends a message under the key `conflict|<slug>|<head 12>`. After the reviewer
has written the review, `github` sends the rebase message instead, whatever `jmerge` says first.
`github` does not wait for `jmerge` here, because a red check hides the conflict from the line
that `jmerge` prints.

The third is a head at which every check passed, under the key `green|<slug>|<head 12>`. `github`
sends this message only where the crew owes a line on green and no reviewer that the crew launched
is still out (`owed`). `github` sends nothing for a green pull request when the crew owes nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from jbriefs import below
from jbriefs.home import thread_of
from jbus import END_TURN, cancelled, dispatch, outbox, queue, review, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import (
    NEVER,
    World,
    checks,
    failed_in,
    job,
    job_log,
    task_brief,
)
from jmerge import lines as lines_of
from jmerge import ready
from jmerge import stacked as stacks
from jmerge.checks import check_state, latest_of_each
from jmerge.lines import Line

EVENTS = {
    "rebase": "quiet",
    "rereview": "quiet",
    "drops": "quiet",
    "failed": "quiet",
    "conflict": "quiet",
    "refailed": "quiet",
    "green": "quiet",
}
STALE = (ready.MAIN_CHANGED.code, ready.CONFLICTS.code)
"""The codes of the `wait` reasons that only a rebase lifts: the default branch changed under the
check, and a conflict with the base."""
NO_THREAD = "stale pull request with no thread to tell"
REFUSED = "T3 Code refused the rebase message"
SECOND = "stale again after its one rebase"
MESSAGE = (
    "jbus: main moved under your pull request #{number} ({reason}). Rebase it in your own "
    "worktree now, even if GitHub says MERGEABLE: run `git update-ref "
    'refs/jstack/pre-rebase/{slug}/{short} {head}` first, then "A conflict"\'s rebase onto '
    "origin/{default}, the check command, and push with `git push "
    "--force-with-lease=refs/heads/{slug}:{head} origin HEAD:refs/heads/{slug}`. Never push "
    "without the lease. jmerge merges only after a new green check."
)


_RANGES = re.compile(r"(git range-diff --no-color (\S+\.\.[0-9a-f]{40}) (\S+\.\.([0-9a-f]{40})))$")
REREVIEW = (
    "jbus: your rebase of pull request #{number} changed its content after its review ({command})."
)
UNRULED = (
    "jbus: your Result explains the lines the rebase of pull request #{number} dropped, and no "
    "scoped review has ruled on them yet ({command})."
)
SCOPED = (
    " If the Result already has a `Scoped reviewer:` line that names this head, launch nothing "
    "more. Otherwise launch ONE scoped reviewer, not a full review, in {{worktree}}: the same way "
    'the crew skill\'s "The review" launches a reviewer, with `workspaceStrategy` '
    "`existing_worktree` on that worktree and the message `/pr-review run {slug} scoped {old} "
    "{new}`. Add `Scoped reviewer: <threadId>, of {head}` to the Result, in place of a `Scoped "
    "reviewer:` line that names another head no `## Review` has. Do not rebase again until its "
    "`## Review` is written. Handle its findings as a review's: a `Finding:` line for each."
)


_AT = re.compile(r" at ([0-9a-f]{12})$")
DROPPED = (
    "jbus: {reason} (pull request #{number}). Put the lines back, commit and push. Or, where "
    "a line is gone on purpose, add one line to the Result for each file, with the counts "
    "above: `Dropped on rebase: <file>, <n> of main's, <m> of its own, at {short}: <why>`. "
    "The scoped review rules on each one. " + END_TURN
)


FAILED = (
    "jbus: {reason} on your pull request #{number} at {short}. In your own worktree, run the "
    'block of "The checks" and do what it prints. ' + END_TURN
)
CONFLICTED = (
    "jbus: your pull request #{number} is in conflict with its base at {short}. In your own "
    'worktree, run the first block of "A conflict" as it is, and do what it prints: it does '
    "not rebase while a review is running. " + END_TURN
)
GREEN = (
    "jbus: every check of your pull request #{number} passed at {short}, and the home is owed "
    'a line on green. In your own worktree, run the block of "The checks", then do what "The '
    'review" says of a green pull request: the message of the `Reviewer: none` line, or the '
    "`fixed and green` line. " + END_TURN
)
_JOB = re.compile(r"^/([^/]+/[^/]+)/actions/runs/\d+/job/(\d+)$")


@dataclass(frozen=True)
class Ask:
    """An `Ask` is one message that jbus sends because of a `wait` line of `jmerge`. It holds the
    message and the head that the message is about."""

    kind: str
    did: str
    doing: str
    message: str
    head: str = ""
    default: bool = False
    no_thread: str = NO_THREAD
    refused: str = REFUSED


def _waits(line: str) -> tuple[Line, str] | None:
    """Return a `wait` line of `jmerge` and its reason's code, or None for any other line. A line
    as `jmerge` prints it has no code, and takes the one its text gives (`ready.code_of`)."""
    said = lines_of.one(line)
    if said is None or said.word != "wait" or not said.reason:
        return None
    return said, said.code or ready.code_of(said.reason)


def content(line: str) -> tuple[int, str, Ask] | None:
    """Return the number of the pull request, the reason that `jmerge` gives, and the scoped review
    that jbus requests. `content` reads a line that waits on a scoped review: of a rebase that
    changed the content, or of drops the Result explains that no review has ruled on. The two
    ranges of the review are the ones the reason's range-diff names."""
    found = _waits(line)
    scoped = {ready.CONTENT_CHANGED.code: REREVIEW, ready.SCOPED_UNRULED.code: UNRULED}
    why = scoped.get(found[1], "") if found else ""
    named = _RANGES.search(found[0].reason) if found and why else None
    if not found or not named:
        return None
    asked = _scoped(why.replace("{command}", named[1]), named[2], named[3])
    return found[0].number, found[0].reason, Ask("rereview", *asked, named[4])


def _scoped(why: str, old: str, new: str) -> tuple[str, str, str]:
    """Return what an ask for a scoped review says when it is done, what it says when it could not
    be done, and its message."""
    message = (why + SCOPED).replace("{old}", old).replace("{new}", new)
    message = message.replace("{head}", new.rpartition("..")[2])
    return "asked the crew for a scoped review", "asked for a scoped review", message


def drops(line: str) -> tuple[int, str, str] | None:
    """Return the number of the pull request, its address, and the first twelve characters of the
    head. `drops` reads a line that waits on a drop nobody explained."""
    found = _waits(line)
    named = _AT.search(found[0].reason) if found and found[1] == ready.DROPPED.code else None
    return (found[0].number, found[0].name, named[1]) if found and named else None


def stale(line: str) -> tuple[int, str] | None:
    found = _waits(line)
    return (found[0].number, found[0].reason) if found and found[1] in STALE else None


def asks(line: str) -> tuple[int, str, Ask] | None:
    """Return the `Ask` that a line of `jmerge` needs, or None when the line needs no message."""
    found = stale(line)
    dropped = None if found else drops(line)
    if dropped:
        number, _, head = dropped
        ask = Ask("drops", "told the crew of the drop", "told of the drop", DROPPED, head)
        return number, line.partition(": ")[2], ask
    if not found:
        return content(line)
    ask = Ask("rebase", "told the crew", "told to rebase", MESSAGE, default=True)
    return *found, ask


def tell(run: Pass, client: Client, world: World, lines: list[str]) -> None:
    """Send one message, once per head, to each crew whose pull request `jmerge` calls stale,
    rebased with its content changed, or short of lines nobody explained or ruled on. A scoped
    review the Result already names a reviewer of at its head is asked for no more."""
    for number, reason, ask in filter(None, map(asks, lines)):
        if ask.kind == "rereview" and scoping(run, world, number, ask.head):
            continue
        deliver(run, client, world, number, reason, ask)


def scoping(run: Pass, world: World, number: int, head: str) -> bool:
    """Say whether the brief of the pull request has a `Scoped reviewer:` line of this head."""
    slug = next((slug for slug, pull in world.open.items() if pull["number"] == number), "")
    return bool(slug and below.reviewers(task_brief(run, slug), "Scoped reviewer", head))


def github(run: Pass, client: Client, world: World) -> None:
    """For each crew, send one message of each kind, once per head, when GitHub says the crew's pull
    request is red, in conflict with its base, or green with a line owed on it."""
    sent = run.box.sent()
    for slug, pull in world.open.items():
        head, number = pull.get("headRefOid", ""), pull["number"]
        if not head or not crew(run, slug):
            continue
        brief = task_brief(run, slug)
        rebased = f"rebase|{slug}|{head[:12]}" in sent
        red = Red() if rebased else ran_and_failed(run, pull)
        again = _asked("refailed", FAILED, head) if red.attempt > 1 else None
        ask = again or _asked("failed", FAILED, head)
        if red.reason and f"{ask.kind}|{slug}|{head[:12]}" not in sent:
            told = f"failure|{slug}|{head[:12]}|{failure(run, red)}"
            merged = "" if again else told_before(run, head, told, sent)
            if merged:
                run.box.mark(f"failed|{slug}|{head[:12]}")
                run.box.mark(told)
                run.say(
                    f"failed {slug}: #{number} at {head[:12]} is a merge of main onto "
                    f"{merged[:12]}, red on the failure its crew was told of, so not told again"
                )
            elif deliver(run, client, world, number, red.reason, ask):
                run.box.mark(told)
        told = rebased or f"conflict|{slug}|{head[:12]}" in sent
        if pull.get("mergeable") == "CONFLICTING" and not told and not stacks.unmoved(brief):
            reason = "it conflicts with its base"
            if review.reviewed(brief):
                ask = Ask("rebase", "told the crew", "told to rebase", MESSAGE, head[:12], True)
            else:
                ask = _asked("conflict", CONFLICTED, head)
            deliver(run, client, world, number, reason, ask)
        green = f"green|{slug}|{head[:12]}" not in sent and checks(pull) == "passed"
        if green and owed(run, brief, head):
            deliver(run, client, world, number, "green", _asked("green", GREEN, head))


def worktree(client: Client, thread: str) -> str | None:
    """Return the thread's `worktreePath` as T3 Code reads it: None where T3 Code says it has none,
    and nothing where the read gave no answer or no such field."""
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Error:
        return ""
    said = (read or {}).get("thread") or {}
    return said.get("worktreePath", "")


def where(client: Client, thread: str) -> str:
    """Name the crew's worktree, by its path where T3 Code gives it."""
    path = worktree(client, thread)
    return f"your worktree, `{path}`" if path else "your own worktree"


def crew(run: Pass, slug: str) -> str:
    """Return the thread of the slug's crew: the one jbus launched, or for a row whose home
    launched its crew itself, the thread its queue row names. Return nothing for a slug with no
    crew of either kind."""
    launched = dispatch.launched(run, slug)
    if launched:
        return launched
    row = queue.fresh(run.state, slug) or {}
    return str(row.get("thread") or "")


def owed(run: Pass, brief: str, head: str) -> bool:
    """Say whether the crew owes a line on green.

    The crew never owes the line while a reviewer that it launched has not yet written a
    `## Review`, since the reviewer's findings decide the line. Otherwise it owes the line where
    the brief's first `Review:` line says `none`, and the brief has no `Reviewer: none` line and
    no `Unrun:`, `Stuck:` or `Stale base:` line at this head. The crew writes the `Reviewer: none`
    line when it sends its message. Each of the other three lines comes with a gate or a message
    that already tells of the pull request. jbus alone merges, so no home waits to hear of a fix
    on green, and a brief that says `Review: after` owes no line.
    """
    if "".join(below.line(brief, "Review:").split()[:1]) != "none":
        return False
    said_none = not all(map(below.launched, below.reviewers(brief, "Reviewer")))
    gated = re.search(rf"^(?:Unrun|Stuck|Stale base): at {re.escape(head)},", brief, re.M)
    return not (review.launched(brief) or said_none or review.reviewed(brief) or gated)


def _asked(kind: str, message: str, head: str) -> Ask:
    what = {
        "failed": "failed check",
        "refailed": "failed rerun",
        "green": "green check",
    }.get(kind, kind)
    return Ask(
        kind,
        "told the crew",
        f"told of the {what}",
        message,
        head[:12],
        no_thread=f"{what} with no thread to tell",
        refused=f"T3 Code refused the {what} message",
    )


MERGER = "web-flow"


@dataclass(frozen=True)
class Red:
    """The failed checks at a pull request's head, among those that ran: `reason` names them, or
    is empty, `attempt` is the highest attempt of the workflow runs they failed in, and `jobs` is
    each one's repo and job, where its link gives them."""

    reason: str = ""
    attempt: int = 0
    names: tuple[str, ...] = ()
    jobs: tuple[tuple[str, str], ...] = ()


def failure(run: Pass, red: Red) -> str:
    """Return the identity of a failure, as the first twelve characters of a digest: the failed
    checks' names, and the pytest ids that their jobs' logs name as failed (`joblog.failed_in`).
    A job whose log GitHub does not give adds no id, so its failure is its check's name."""
    import hashlib

    tests = set()
    for repo, number in red.jobs:
        log = job_log(run, repo, number)
        tests.update(failed_in(log).tests if log is not None else ())
    said = "\n".join([*sorted(set(red.names)), "", *sorted(tests)])
    return hashlib.sha256(said.encode()).hexdigest()[:12]


def told_before(run: Pass, head: str, told: str, sent: list[str]) -> str:
    """Return the head that this one merged main onto, where its crew was told of this same
    failure (`told`) at that head, or nothing. Such a head is GitHub's merge of the base into the
    branch, as update-branch makes it: a commit by `web-flow` with two parents, the branch's head
    first. A head the crew pushed is never such a head, so it is told whatever it fails on.

    Beside each `failed|<slug>|<head 12>` key, `github` writes what it told,
    `failure|<slug>|<head 12>|<failure>`, the failure being `failure`'s digest of the failed checks'
    names and the pytest ids their jobs' logs name. For a head this returns one for, `github` sends
    nothing and marks both keys as if told. So a crew hears once of a failure, however often main
    is merged in (#494, 2026-10-26: jmerge's update-branch made nine heads, each red on the same
    test, and each was a `failed` message to a capped crew)."""
    asked = run.run("gh", "api", f"repos/{{owner}}/{{repo}}/commits/{head}")
    try:
        commit = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        commit = {}
    if not isinstance(commit, dict) or (commit.get("committer") or {}).get("login") != MERGER:
        return ""
    parents = [str((one or {}).get("sha") or "") for one in commit.get("parents") or []]
    if len(parents) != 2 or not parents[0]:
        return ""
    same = told.replace(f"|{head[:12]}|", f"|{parents[0][:12]}|")
    return parents[0] if same in sent else ""


def ran_and_failed(run: Pass, pull: dict) -> Red:
    """Return the failed checks at the pull request's head, among the checks that ran, as a `Red`:
    its `reason` names them, or is empty, beside their names, their jobs and the highest attempt of
    the workflow runs in which they failed. When
    GitHub says a check's job ran no step, the check never started: CI started no job, and the
    crew's `unrun` parks that case. When GitHub will not give a check's job, the check counts as
    run, at its first attempt. A workflow run in which a cancelled or timed-out job stopped a
    required check is `cancelled`'s, which runs it again or tells the home, so none of its checks
    is named here."""
    if checks(pull) != "failed":
        return Red()
    names, jobs, attempt, required = [], [], 1, cancelled.required(run)
    never = frozenset(pull.get(NEVER) or ())
    latest = latest_of_each(pull.get("statusCheckRollup") or [])
    theirs = cancelled.runs(latest, never, required)
    for check in latest:
        if (
            check_state(check, never) != "failed"
            or cancelled.run_of(check.get("detailsUrl")) in theirs
        ):
            continue
        found = _JOB.match(urlsplit(check.get("detailsUrl") or "").path)
        given = job(run, *found.groups()) if found else {}
        attempt = max(attempt, int(given.get("run_attempt") or 1))
        names.append(check.get("name") or check.get("context") or "a check")
        jobs.extend([found.groups()] if found else [])
    if not names:
        return Red()
    return Red(f"{', '.join(dict.fromkeys(names))} failed", attempt, tuple(names), tuple(jobs))


def deliver(run: Pass, client: Client, world: World, number: int, reason: str, ask: Ask) -> bool:
    """Send the crew of a pull request one message, once per head, and write an event of the ask's
    kind that says so. Say whether the message went."""
    sent = post(run, client, world, number, reason, ask)
    if sent:
        slug, head, message = sent
        line = f"{ask.kind} {slug}: {ask.did} (#{number}, {head[:12]})"
        run.find(slug, ask.kind, line, message, key=head[:12])
        run.say(line)
    return bool(sent)


def mark(kind: str, slug: str, head: str, window: str = "") -> str:
    """Return the key of a message about a head: `<kind>|<slug>|<head 12>`, and `|<window>` after
    it where the caller names one, as a restack names the base it moves onto (`jbus.stack`)."""
    return f"{kind}|{slug}|{head[:12]}" + (f"|{window}" if window else "")


def post(
    run: Pass, client: Client, world: World, number: int, reason: str, ask: Ask, window: str = ""
) -> tuple[str, str, str] | None:
    """Send the crew of a pull request one message. Return the slug, the head and the message sent,
    or nothing when no message went.

    `post` sends only for a pull request that is open under a slug that has a crew (`crew`): jbus
    launched it, or its home launched it for a queue row that names its thread. The key `mark`
    gives is the retry key at T3 Code. `post` sends no message whose key is already in `sent.json`.
    `deliver` puts the key there through the event that it queues, and any other caller writes the
    key itself. `mainmoved` also writes the key, for a head that it told.
    `post` sends nothing while `held` delays the message, or while the outbox holds it for a capped
    instance (`jbus.outbox`): the message waits under its key, and the first pass after the reset
    sends it. When a rebase message goes, `post` writes
    the `mainmoved` key for the commit that the default branch points to, so jbus does not also
    tell of that move.
    """
    slug = next((slug for slug, pull in world.open.items() if pull["number"] == number), "")
    head = world.open[slug].get("headRefOid", "") if slug else ""
    key = mark(ask.kind, slug, head, window)
    if not head or not crew(run, slug):
        return None
    sent = run.box.sent()
    if key in sent:
        return None
    if ask.head and not head.startswith(ask.head):
        return None
    again = any(mark.startswith(f"rebase|{slug}|") for mark in sent)
    if ask.kind == "rebase" and again and ready.code_of(reason) != ready.CONFLICTS.code:
        run.gate(slug, SECOND, f"#{number}: {reason}", key=f"{SECOND} {head[:12]}")
        return None
    thread = thread_of(run.home, slug)
    if not thread:
        run.gate(slug, ask.no_thread, f"#{number}: {reason}", key=f"{ask.no_thread} {head[:12]}")
        return None
    default = ""
    if ask.default:
        asked = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
        default = asked.stdout.strip().removeprefix("origin/")
    if ask.default and not default:
        run.say(f"wait {slug}: the default branch is not known, so its crew is not told")
        return None
    if held(run, client, thread, slug, number, head, key, ask.kind):
        return None
    message = ask.message.format(
        number=number, reason=reason, slug=slug, short=head[:12], head=head, default=default
    )
    if "{worktree}" in message:
        message = message.replace("{worktree}", where(client, thread))
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=slug,
            key=key,
            text=message,
            template=ask.kind,
            needs="act",
        )
    except T3Refused as error:
        run.gate(slug, ask.refused, f"{error}\n\n{message}", key=f"{ask.refused} {head[:12]}")
        return None
    except T3Error as error:
        run.say(f"wait {slug}: its crew could not be {ask.doing} ({error})")
        return None
    if not went:
        return None
    if ask.default:
        asked = run.run("git", "ls-remote", "origin", f"refs/heads/{default}")
        main = (asked.stdout.split() or [""])[0]
        if asked.returncode == 0 and main:
            run.box.mark(f"mainmoved|{slug}|#{number}|{main[:12]}")
    return slug, head, message


def held(
    run: Pass, client: Client, thread: str, slug: str, number: int, head: str, key: str, kind: str
) -> bool:
    """Say whether this pass delays a message that names this head.

    The outbox may hold it (`outbox.hold`): a thread at work would read it only after its turn,
    and that turn may move the head, and a thread that waits on a test slot or on its review puts
    it off. `held` asks the outbox first, so it asks GitHub nothing for a message the outbox would
    hold. The head is the one that the pass listed, and a push since then may have replaced it.
    So `held` asks GitHub again, and no message names a head that GitHub does not confirm.
    """
    if outbox.hold(run, client, thread=thread, row=slug, key=key, template=kind, needs="act"):
        return True
    asked = run.run("gh", "pr", "view", str(number), "--json", "headRefOid")
    try:
        now = json.loads(asked.stdout).get("headRefOid", "") if asked.returncode == 0 else ""
    except (ValueError, AttributeError):
        now = ""
    if now != head:
        left = f"is at {now[:12]} now" if now else "could not be asked for its head"
        run.say(f"wait {slug}: #{number} {left}, so its crew is not told of {head[:12]}")
        return True
    return False


STEPS = (
    verbs.Step(
        "tellers",
        100,
        "rebase.tell",
        lambda half: tell(half.run, half.client, half.seen.world, half.said),
        ("client", "world"),
    ),
    verbs.Step(
        "after-expedite",
        30,
        "rebase.github",
        lambda half: github(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
