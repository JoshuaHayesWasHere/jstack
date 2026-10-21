"""Telling a crew to rebase: the safety that a shared file no longer buys at launch.

No row waits for another brief's files, so two crews may change the same file, each in its
own worktree. The merge decides: `jmerge` waits on a pull request the default branch moved
under, or that conflicts with its base, and says so on a `wait` line. `tell` reads those
lines and sends the crew one message for each head, with a backup ref for the head it
rewrites and a lease that names it, so a rebase never loses what was there.

The message's key, `rebase|<slug>|<head 12>`, is its retry key at T3 Code and its mark in
`sent.json`, so a pass that got no answer tries again and a head that was told is not told
twice. A pull request is told to rebase once for main moving or a failure: a crew that
rebased and is stale or failing again at a new head gets a gate (`SECOND`), with the default
that the pull request waits, and no second rebase. A conflict with its base is told at every
head: nothing but a rebase resolves it.

A rebase that changed what the patch says is the other line `tell` reads. `jmerge` carries
a review over a rebase whose range-diff changes no content, and waits on one that does:
its crew is asked for one scoped review of that range-diff, under the key
`rereview|<slug>|<head 12>`, so a head is asked once and reviews never stack.

A rebase that dropped lines nobody explained is the third. `jmerge` waits on it, and its
crew is told once per head, under the key `drops|<slug>|<head 12>`: put the lines back, or
say of each file why they are gone, which the scoped review then rules on.

`deliver` is the one way such a message goes, and `stall` uses it too, for a line this module
does not read: a guarded pull request whose fix no review has proved (`unproven`), under the
key `proof|<slug>|<head 12>`. `post` is the message without the event, which `expedite` says
in its own.

Each of them names a head, and is sent with `mode: queue`, so it is read in a turn of its
own, after whatever turn is running. `held` keeps one back for a pass in the two cases where
it would be read about a head that is gone: the crew's thread is at work, or the pull request
left the head since the pass listed it. Both are asked again at the send, of T3 Code and of
GitHub, since a pass sends other messages first. A thread this pass already sent one to is
at work too, so a pass sends a thread one of them. Nothing is marked for a message kept
back, so the next pass decides again from the head and the reason there are then.

`mainmoved` asks `held` too, and the two tell a crew to rebase one head once between them.
The rebase message marks `mainmoved`'s key for the commit main is at, and `mainmoved` marks
this module's key for the head it told, whichever of the two reaches it first.

No watch of T3 Code's wakes a crew: `github` tells it what GitHub says it must act on, each
through `deliver`. A check that ran and failed at a head, under the key
`failed|<slug>|<head 12>`, and once more under `refailed|<slug>|<head 12>` when it fails
again in a later attempt of its workflow run, which the crew's one rerun of a head starts.
One that failed with no step run is a CI that started no job, which no push repairs, and is
not told, and a head the rebase message went to is told to rebase, which is what its failed
check asks. A conflict with its base at a head, which before the review is written goes
under the key `conflict|<slug>|<head 12>`, and after it is the rebase message, whatever
`jmerge` says first: a red check hides the conflict from its line. And every check passed at
a head, under the key `green|<slug>|<head 12>`, only where the crew owes a line on green and
no reviewer it launched is still out (`owed`). A green pull request with nothing owed is
told nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from jbus import END_TURN, dispatch, merge, read_json, verbs
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import LIVE, TITLE, World, checks, crew_threads
from jmerge import ready

EVENTS = {
    "rebase": "quiet",
    "rereview": "quiet",
    "drops": "quiet",
    "proof": "quiet",
    "failed": "quiet",
    "conflict": "quiet",
    "refailed": "quiet",
    "green": "quiet",
}
_WAIT = re.compile(r"^wait (\d+) \S+: (.+)$")
_HEAD = re.compile(r"\bfails on ([0-9a-f]{12}) over today's main")
CONFLICT = re.compile(r"\bconflicts with its base")
STALE = (re.compile(r"\bchanged .+ after its check started"), _HEAD, CONFLICT)
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


_CONTENT = re.compile(
    r"\b"
    + re.escape(ready.CONTENT_CHANGED.removesuffix("{command}"))
    + r"(git range-diff --no-color (\S+\.\.[0-9a-f]{40}) (\S+\.\.([0-9a-f]{40})))$"
)
REREVIEW = (
    "jbus: your rebase of pull request #{number} changed its content after its review ({command})."
)
UNPROVEN = (
    "jbus: the fix you pushed to pull request #{number} has no review at its head, and jmerge "
    "waits on it ({reason})."
)
SCOPED = (
    " If the Result already has a `Scoped reviewer:` line that names this head, launch nothing "
    "more. Otherwise launch ONE scoped reviewer, not a full review: the same way the crew "
    'skill\'s "The review" launches a reviewer, with the message `/pr-review run {slug} scoped '
    "{old} {new}`. Add `Scoped reviewer: <threadId>, of {head}` to the Result, in place of a "
    "`Scoped reviewer:` line that names another head no `## Review` has. Do not rebase again "
    "until its `## Review` is written. Handle its findings as a review's: a `Finding:` line for "
    "each."
)


DROPS = re.compile(
    r"^wait (\d+) (\S+): the rebase dropped .+ with no Dropped on rebase line at ([0-9a-f]{12})"
)
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
_OWED = re.compile(r"^Reviewer: none\b", re.M)
_LAUNCHED = re.compile(r"^(?:Reviewer|Second reviewer|Scoped reviewer): (?!none\b)\S", re.M)
_REVIEWED = re.compile(r"^## Review\n(?:(?!## ).*\n)*?Head: ", re.M)
_MODE = re.compile(r"^Review:[ \t]*(\S*)", re.M)
_FIXED = re.compile(r"^Fixed: \S", re.M)
_JOB = re.compile(r"^/([^/]+/[^/]+)/actions/runs/\d+/job/(\d+)$")
_FAILING = ("SUCCESS", "NEUTRAL", "SKIPPED", "PENDING", "EXPECTED", "")


@dataclass(frozen=True)
class Ask:
    """One message a `wait` line of `jmerge` asks for: what it is, and the head it is about."""

    kind: str
    did: str
    doing: str
    message: str
    head: str = ""
    default: bool = False
    no_thread: str = NO_THREAD
    refused: str = REFUSED


def content(line: str) -> tuple[int, str, Ask] | None:
    """The pull request's number, `jmerge`'s reason and the scoped review to ask for, for a
    line that waits on one."""
    found = _WAIT.match(line)
    named = found and _CONTENT.search(found[2])
    if not found or not named:
        return None
    asked = _scoped(REREVIEW.replace("{command}", named[1]), named[2], named[3])
    return int(found[1]), found[2], Ask("rereview", *asked, named[4])


def unproven(old: str, new: str) -> Ask:
    """The scoped review to ask for of a fix no review has proved: the two ranges are the
    patch up to the head the last review saw, and the patch up to the head."""
    return Ask("proof", *_scoped(UNPROVEN, old, new), new.rpartition("..")[2])


def _scoped(why: str, old: str, new: str) -> tuple[str, str, str]:
    """What an ask for a scoped review says was done, could not be done, and its message."""
    message = (why + SCOPED).replace("{old}", old).replace("{new}", new)
    message = message.replace("{head}", new.rpartition("..")[2])
    return "asked the crew for a scoped review", "asked for a scoped review", message


def drops(line: str) -> tuple[int, str, str] | None:
    """The pull request's number, what `jmerge` prints after it, and the head's first
    twelve characters, for a line that waits on a drop nobody explained."""
    found = DROPS.match(line)
    return (int(found[1]), found[2], found[3]) if found else None


def stale(line: str) -> tuple[int, str] | None:
    found = _WAIT.match(line)
    if found and any(reason.search(found[2]) for reason in STALE):
        return int(found[1]), found[2]
    return None


def asks(line: str) -> tuple[int, str, Ask] | None:
    """What a line of `jmerge` asks its crew for, or None for a line that asks for nothing."""
    found = stale(line)
    dropped = None if found else drops(line)
    if dropped:
        number, _, head = dropped
        ask = Ask("drops", "told the crew of the drop", "told of the drop", DROPPED, head)
        return number, line.partition(": ")[2], ask
    if not found:
        return content(line)
    named = _HEAD.search(found[1])
    ask = Ask("rebase", "told the crew", "told to rebase", MESSAGE, named[1] if named else "", True)
    return *found, ask


def tell(run: Pass, client: Client, world: World, lines: list[str]) -> None:
    """Send each crew whose pull request `jmerge` calls stale, rebased with its content
    changed, or short of lines nobody explained, one message, once per head."""
    for number, reason, ask in filter(None, map(asks, lines)):
        deliver(run, client, world, number, reason, ask)


def github(run: Pass, client: Client, world: World) -> None:
    """Send each crew whose pull request GitHub says is red, in conflict with its base, or
    green with a line owed on it, one message of each, once per head."""
    sent = read_json(run.state / "sent.json", [])
    for slug, pull in world.open.items():
        head, number = pull.get("headRefOid", ""), pull["number"]
        if not head or not dispatch.launched(run, slug):
            continue
        brief = _brief(run, slug)
        rebased = f"rebase|{slug}|{head[:12]}" in sent
        failed, attempt = ("", 0) if rebased else ran_and_failed(run, pull)
        again = _asked("refailed", FAILED, head) if attempt > 1 else None
        ask = again or _asked("failed", FAILED, head)
        if failed and f"{ask.kind}|{slug}|{head[:12]}" not in sent:
            deliver(run, client, world, number, failed, ask)
        told = rebased or f"conflict|{slug}|{head[:12]}" in sent
        if pull.get("mergeable") == "CONFLICTING" and not told:
            reason = "it conflicts with its base"
            if _REVIEWED.search(brief):
                ask = Ask("rebase", "told the crew", "told to rebase", MESSAGE, head[:12], True)
            else:
                ask = _asked("conflict", CONFLICTED, head)
            deliver(run, client, world, number, reason, ask)
        green = f"green|{slug}|{head[:12]}" not in sent and checks(pull) == "passed"
        if green and owed(run, brief, head):
            deliver(run, client, world, number, "green", _asked("green", GREEN, head))


def _brief(run: Pass, slug: str) -> str:
    try:
        return (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        return ""


def owed(run: Pass, brief: str, head: str) -> bool:
    """Whether the crew owes a line on green. Never while a reviewer it launched has written
    no `## Review` yet: what it finds decides the line. Otherwise a pull request whose
    brief's first `Review:` line says `none`, with no `Reviewer: none` line, which the crew
    writes with its message, and no `Unrun:`, `Stuck:` or `Stale base:` line at this head,
    whose gate or message already holds it. Or one that is fixed while a home merges, which
    hears of it on green alone. A brief that says `Review: after` merges on green whatever
    its review says, so it is owed the line while a home merges, its reviewer out or not."""
    mode = _MODE.search(brief)
    if mode and mode[1] == "after":
        return bool(merge.home_thread(run))
    launched = len(_LAUNCHED.findall(brief))
    if launched > len(_REVIEWED.findall(brief)):
        return False
    gated = re.search(rf"^(?:Unrun|Stuck|Stale base): at {re.escape(head)},", brief, re.M)
    reviewer = launched or _OWED.search(brief) or _REVIEWED.search(brief) or gated
    unsaid = not reviewer and mode and mode[1] == "none"
    return bool(unsaid or (merge.home_thread(run) and _FIXED.search(brief)))


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


def ran_and_failed(run: Pass, pull: dict) -> tuple[str, int]:
    """What failed at the pull request's head among the checks that ran, as `{reason}`, or
    nothing, and the highest attempt of the workflow runs it failed in. A check whose job
    GitHub says ran no step never started: a CI that started no job, which the crew's `unrun`
    parks. One whose job GitHub will not give counts as run, at its first attempt."""
    if checks(pull) != "failed":
        return "", 0
    names, attempt = [], 1
    for check in pull.get("statusCheckRollup") or []:
        state = check.get("state") or check.get("conclusion") or ""
        if check.get("status", "COMPLETED") != "COMPLETED" or state in _FAILING:
            continue
        job = _JOB.match(urlsplit(check.get("detailsUrl") or "").path)
        given = _job(run, *job.groups()) if job else {}
        if given.get("steps") == []:
            continue
        attempt = max(attempt, int(given.get("run_attempt") or 1))
        names.append(check.get("name") or check.get("context") or "a check")
    if not names:
        return "", 0
    return f"{', '.join(dict.fromkeys(names))} failed", attempt


def _job(run: Pass, repo: str, job: str) -> dict:
    asked = run.run("gh", "api", f"repos/{repo}/actions/jobs/{job}")
    try:
        given = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        given = {}
    return given if isinstance(given, dict) else {}


def deliver(run: Pass, client: Client, world: World, number: int, reason: str, ask: Ask) -> None:
    """Send the crew of a pull request one message, once per head, and say so in an event of
    the ask's kind."""
    sent = post(run, client, world, number, reason, ask)
    if sent:
        slug, head, message = sent
        line = f"{ask.kind} {slug}: {ask.did} (#{number}, {head[:12]})"
        run.find(slug, ask.kind, line, message, key=head[:12])
        run.say(line)


def post(
    run: Pass, client: Client, world: World, number: int, reason: str, ask: Ask
) -> tuple[str, str, str] | None:
    """Send the crew of a pull request one message. The answer is the slug, the head and the
    message that went, or nothing where none did.

    Only a pull request that is open under a slug jbus launched: any other is not its crew.
    The key, `<kind>|<slug>|<head 12>`, is the retry key at T3 Code, and one that is in
    `sent.json` is not sent again: the event `deliver` queues puts it there, and any other
    caller marks it. So does `mainmoved`, for a head it told. None goes while `held` keeps
    it back. A rebase message that went marks `mainmoved`'s key for the commit the default
    branch is at, so that move is not told too.
    """
    slug = next((slug for slug, pull in world.open.items() if pull["number"] == number), "")
    head = world.open[slug].get("headRefOid", "") if slug else ""
    key = f"{ask.kind}|{slug}|{head[:12]}"
    if not head or not dispatch.launched(run, slug):
        return None
    sent = read_json(run.state / "sent.json", [])
    if key in sent:
        return None
    if ask.head and not head.startswith(ask.head):
        return None
    again = any(mark.startswith(f"rebase|{slug}|") for mark in sent)
    if ask.kind == "rebase" and again and not CONFLICT.search(reason):
        run.gate(slug, SECOND, f"#{number}: {reason}", key=f"{SECOND} {head[:12]}")
        return None
    try:
        brief = (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        brief = ""
    thread = dispatch.thread_of(brief)
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
    if held(run, client, world, slug, number, head):
        return None
    message = ask.message.format(
        number=number, reason=reason, slug=slug, short=head[:12], head=head, default=default
    )
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
    try:
        client.call("t3_thread_send", asked)
    except T3Refused as error:
        run.gate(slug, ask.refused, f"{error}\n\n{message}", key=f"{ask.refused} {head[:12]}")
        return None
    except T3Error as error:
        run.say(f"wait {slug}: its crew could not be {ask.doing} ({error})")
        return None
    run.told.add(slug)
    if ask.default:
        asked = run.run("git", "ls-remote", "origin", f"refs/heads/{default}")
        main = (asked.stdout.split() or [""])[0]
        if asked.returncode == 0 and main:
            run.box.mark(f"mainmoved|{slug}|#{number}|{main[:12]}")
    return slug, head, message


def held(run: Pass, client: Client, world: World, slug: str, number: int, head: str) -> bool:
    """Whether a message that names this head is kept back in this pass.

    A thread at work (`watch.LIVE`, as `expedite` reads it) would read it after its turn,
    which may move the head. The status the pass listed is from before its other messages
    went, a relay of findings or an answer among them, so T3 Code is asked again. One this
    pass already sent such a message is on `Pass.told`, and is at work whatever T3 Code
    says yet. And the head is the one the pass listed, which a push since made the old one:
    GitHub is asked again, and a head it does not confirm is not named.
    """
    busy = slug in run.told or _live(world.threads.get(slug, []))
    try:
        again = [] if busy else crew_threads(client, run.project.project_id, TITLE + slug)
    except T3Error as error:
        run.say(f"wait {slug}: its thread could not be asked for ({error}), so it is told nothing")
        return True
    mine = (t for t in again if t["title"][len(TITLE) :].strip() == slug and not t.get("settled"))
    if busy or _live(mine):
        run.say(f"wait {slug}: its thread is at work, so its crew is not told of {head[:12]} yet")
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


def _live(threads) -> bool:
    return any(thread["status"] in LIVE for thread in threads)


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
