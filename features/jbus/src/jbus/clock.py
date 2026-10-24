"""Every wait on the system has a clock: a pull request that waits on a reviewer that never writes,
or on a crew that stopped, is asked again by how long it has waited, not by how often `jmerge`
repeats its line.

`tick` reads what jbus's own run of `jmerge` says in this pass of each open pull request that jbus
launched a crew for, and sorts the wait into one of three classes. Where the home merges, acting on
a pull request is the home's (`merge.shown`), so no clock runs there. The classes:

- `review`: the review is not written (`it has no review yet`, `its review has no verdict`, the
  second review or the second pass is not written);
- `scoped`: the scoped review of a fix or a rebase is not written or has not ruled;
- `result`: no Result names the pull request, so the crew stopped before it wrote one.

Each wait has one thread it waits on. For `review` and `scoped` that is the reviewer the brief's
last `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` line names, and the crew where the brief
names none, or where jbus cannot work out a scoped pass's two ranges. For `result` it is the crew
on the brief's `Thread:` line. `clock.json` counts, for each slug, the passes of one wait at one
head in which that thread was not at work: its turn ended, it hung, or T3 Code no longer lists
it. A thread at work (`moving`, `quiet` or `waiting`) stops the count and does not reset it, so a
long review that is still working is never asked again.

At `PASSES` such passes jbus acts once by itself. It sends a reviewer its line again, with
`t3_thread_send`: `/pr-review run <slug> again`, or the scoped line with its two ranges, alone,
since the reviewer's Start reads the line as its message. It sends a crew one carry-on that names
the wait. The count starts again. At `PASSES` more, the second miss, jbus sends the brief's home
one line and owns the wait no longer. With no home, or a home T3 Code refuses the line, it logs
one quiet `stall` instead. Neither goes to the user. A turn that hangs is counted as stopped, and
jbus does not interrupt it: interrupting a hung turn waits on the user's own rule for it
(jv-hung-interrupt), so the home picks it up.

A new head or a new class starts a new clock, and a slug that waits no more drops its clock. A pass
in which `jmerge` failed, or that could not list the threads, counts nothing and keeps the clocks.
A crew that waits on a usage limit (`Pass.limited`) or on a gate is left to `failover` and the
gate. A thread that ended with no Result and no pull request is `threads.resume`'s.
"""

from __future__ import annotations

import re
from typing import Any

from jbriefs.home import home_of, thread_of
from jbus import dispatch, expedite, merge, read_json, threads, verbs, watch, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World
from jmerge import ready

EVENTS = {"clock": "quiet"}
CLOCK = "clock"
STALL = "stall"
FILE = "clock.json"
PASSES = 10
AT_WORK = ("moving", "quiet", "waiting")
FIXES = (ready.FIX_UNREVIEWED, ready.DECLINES_UNRULED)
CLASSES = (
    ("result", (ready.NO_BRIEF,)),
    ("scoped", (*FIXES, ready.SCOPED_UNRULED, ready.CONTENT_CHANGED)),
    ("review", (ready.NO_REVIEW, ready.NO_VERDICT, ready.TWICE_UNWRITTEN, ready.SECOND_UNWRITTEN)),
)
"""Each class with the reasons of `jmerge` it takes, matched by each reason's own pattern, so a
reason that `jmerge` rewords keeps its clock."""
CARRY_ON = (
    "jbus: pull request #{number} of this task has waited {passes} passes on you, with your "
    "thread not at work: {reason}. Carry on with your brief from where you stopped: read "
    "`tasks/{slug}.md` and your worktree's `git status` and `git log` first, keep what is "
    "committed, do not start over, and do what the crew skill says next for your pull request."
)
HOME = (
    "jbus: {slug}'s pull request #{number} still waits, {reason}, {passes} passes after jbus "
    "{did}, with {thread} not at work. It is the home's from here: pick it up as the home skill's "
    '"Picking up a thread that stopped" says. Its crew\'s thread is {crew}.'
)
_SEAT = re.compile(r"#(\d+)$")


def _of(reason: str, reasons: tuple[ready.Reason, ...]) -> bool:
    return any(re.fullmatch(one.pattern, reason) for one in reasons)


def class_of(reason: str) -> str:
    """Return the class of a wait `jmerge` gives, or nothing for a wait that has no clock here."""
    return next((name for name, reasons in CLASSES if _of(reason, reasons)), "")


def _id(line: str) -> str:
    """Return the thread a reviewer line names after its label, or nothing for `none`."""
    found = "".join(line.partition(":")[2].split()[:1]).rstrip(",")
    return "" if found == "none" else found


def reviewer(brief: str, kind: str, reason: str, head: str) -> str:
    """Return the thread of the reviewer that a wait is for, or nothing where the brief names none.

    For a scoped wait it is the last `Scoped reviewer:` line of this head, or else the last one.
    For a second review it is the last `Second reviewer:` line. Otherwise it is the last
    `Reviewer:` line whose seat, `#<n>`, has written no `## Review` with that seat on its `By:`
    line."""
    lines = brief.splitlines()
    if kind == "scoped":
        named = [line for line in lines if line.startswith("Scoped reviewer:")]
        named = [line for line in named if line.split()[-2:] == ["of", head]] or named
    elif "second" in reason:
        named = [line for line in lines if line.startswith("Second reviewer:")]
    else:
        wrote = set(re.findall(r"^By: .* #(\d+)$", brief, re.M))
        named = [line for line in lines if line.startswith("Reviewer:")]
        named = [line for line in named if (s := _SEAT.search(line)) is None or s[1] not in wrote]
    return next((found for found in map(_id, reversed(named)) if found), "")


def _brief(run: Pass, slug: str) -> str:
    try:
        return (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        return ""


def _ask(run: Pass, slug: str, kind: str, reason: str, head: str, brief: str) -> tuple[str, str]:
    """Return the thread a wait is on and the line jbus sends it: the reviewer's line, or nothing
    where the crew is the one to carry on."""
    if kind == "result":
        return dispatch.thread_of(brief), ""
    named = reviewer(brief, kind, reason, head)
    if not named and kind == "review" and expedite.no_reviewer_by_rule(brief, head):
        return "", ""
    if not named:
        return dispatch.thread_of(brief), ""
    if kind == "review":
        return named, expedite.AGAIN.format(slug=slug)
    found = expedite.ranges(run, slug, head, "fix" if _of(reason, FIXES) else "rebase")
    if not found:
        return dispatch.thread_of(brief), ""
    return named, expedite.SCOPED.format(slug=slug, old=found[0], new=found[1])


def _send(run: Pass, client: Client, thread: str, message: str, key: str) -> str:
    """Queue one message to a thread, once for the key. Return `sent`, or `refused` where T3 Code
    refused it, as it does for a thread that is gone, which no later pass would change, or nothing
    for a call that got no answer, which the next pass tries again."""
    if key in run.box.sent():
        return "sent"
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
    try:
        client.call("t3_thread_send", asked)
    except T3Refused as error:
        run.say(f"wait {key.split('|')[1]}: T3 Code refused {thread} its clock's line ({error})")
        run.box.mark(key)
        return "refused"
    except T3Error as error:
        run.say(f"wait {key.split('|')[1]}: {thread} could not be sent its clock's line ({error})")
        return ""
    run.box.mark(key)
    return "sent"


def _act(run: Pass, client: Client, slug: str, wait: dict[str, Any]) -> bool:
    """Send the thread a wait is on its line or a carry-on, once. Return whether it went."""
    number, reason, line = wait["number"], wait["reason"], wait["line"]
    key = f"{CLOCK}|{slug}|{wait['kind']} {wait['head'][:12]} {wait['thread']}"
    if not line:
        line = threads.resume_message(
            CARRY_ON,
            f"crew: {slug}",
            run.home,
            number=number,
            passes=wait["passes"],
            reason=reason,
            slug=slug,
        )
    went = _send(run, client, wait["thread"], line, key)
    if not went:
        return False
    did = "relaunched its reviewer" if wait["line"] else "carried its crew on"
    did += ", and T3 Code refused it" if went == "refused" else ""
    said = f"{CLOCK} {slug}: #{number} waited {wait['passes']} passes on {reason}; {did}"
    run.find(slug, CLOCK, f"{said}, {wait['thread']}", line, key=key.split("|", 2)[2])
    run.say(f"{said}, {wait['thread']}")
    return True


def _home(run: Pass, client: Client, slug: str, wait: dict[str, Any], brief: str) -> bool:
    """Tell the brief's home, in one line, that a wait jbus acted on still waits. With no home, log
    one quiet stall, and one too where T3 Code refused the home the line. Return whether it is
    done."""
    did = "relaunched its reviewer" if wait["line"] else "carried its crew on"
    crew = dispatch.thread_of(brief) or "not known"
    text = HOME.format(
        slug=slug,
        number=wait["number"],
        reason=wait["reason"],
        passes=wait["passes"],
        did=did,
        thread=wait["thread"],
        crew=crew,
    )
    at = thread_of(home_of(run.home, brief))
    key = f"{wait['kind']} {wait['head'][:12]} {wait['thread']}"
    went = _send(run, client, at, text, f"{CLOCK}-home|{slug}|{key}") if at else "no home"
    if not went:
        return False
    if went == "sent":
        run.say(f"{CLOCK} {slug}: told its home, thread {at}, that #{wait['number']} still waits")
        return True
    why = f"T3 Code refused its home, {at}, the line" if at else "it has no home to tell"
    line = f"{STALL} {slug}: #{wait['number']} waited {wait['passes']} passes after jbus {did}"
    line += f", {wait['reason']}, and {why}; its crew's thread is {crew}"
    run.find(slug, STALL, line, key=f"{CLOCK} {key}")
    return True


def tick(
    run: Pass, client: Client, world: World, pulls: merge.Said, out: list[dict[str, Any]] | None
) -> None:
    """Count one pass on each wait's clock, and act on each wait that is due. See the module."""
    waits = watch.waits(pulls)
    was: dict[str, Any] = read_json(run.state / FILE, {})
    if waits.failed or out is None:
        return
    live = {one["id"]: one["live"] for one in out}
    reviewing = {one["slug"] for one in out if one["role"] == "reviewer" and one["live"] in AT_WORK}
    kept: dict[str, Any] = {}
    for slug, pull in sorted(world.open.items()):
        word, _, reason = waits.said.get(str(pull["number"]), "").partition(": ")
        kind, head = class_of(reason), pull.get("headRefOid", "")
        if word != "wait" or not kind or not head:
            continue
        if not dispatch.launched(run, slug) or slug in run.limited or slug in run.gated:
            continue
        brief = _brief(run, slug)
        thread, line = _ask(run, slug, kind, reason, head, brief)
        if not thread:
            continue
        seen = was.get(slug, {})
        same = (seen.get("kind"), seen.get("head"), seen.get("thread")) == (kind, head, thread)
        wait = seen if same else {"passes": 0, "acted": False, "home": False}
        wait = {**wait, "kind": kind, "head": head, "thread": thread, "line": line}
        wait |= {"number": pull["number"], "reason": reason}
        kept[slug] = wait
        busy = {live.get(thread), live.get(dispatch.thread_of(brief))} & set(AT_WORK)
        if wait["home"] or busy or slug in reviewing:
            continue
        wait["passes"] += 1
        if wait["passes"] < PASSES:
            continue
        if not wait["acted"] and _act(run, client, slug, wait):
            wait |= {"acted": True, "passes": 0}
        elif wait["acted"] and _home(run, client, slug, wait, brief):
            wait["home"] = True
    if kept != was:
        write_json(run.state / FILE, kept)


STEPS = (
    verbs.Step(
        "after-expedite",
        15,
        "clock.tick",
        lambda half: tick(half.run, half.client, half.seen.world, half.said, half.out),
        ("client", "world"),
    ),
)
