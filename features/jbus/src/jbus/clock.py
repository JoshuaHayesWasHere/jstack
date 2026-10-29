"""Every wait on the system has a clock: a pull request that waits on a reviewer that never writes,
or on a crew that stopped, is asked again by how long it has waited, not by how often `jmerge`
repeats its line.

`tick` reads what jbus's own run of `jmerge` says in this pass of each open pull request that jbus
launched a crew for, and sorts the wait into one of three classes:

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
`jbus.outbox`: `/pr-review run <slug> again`, or the scoped line with its two ranges, alone,
since the reviewer's Start reads the line as its message. A scoped reviewer that T3 Code says has
no `worktreePath` runs in the main checkout and refuses there, so it is sent nothing: its crew is
told instead (`ROOTED`), once for the head, to launch one in the crew's own worktree. It sends a
crew one carry-on that names the wait. The count starts again. At `PASSES` more, the second miss,
jbus logs one quiet `stall` and owns the wait no longer: the stall is an item of the one list,
which takes it to the brief's home (`jbus.wakes`), and never to the user. A turn that hangs is
counted as stopped, and jbus does not interrupt it: interrupting a hung turn waits on the user's
own rule for it (jv-hung-interrupt), so the home picks it up.

A new head or a new class starts a new clock, and a slug that waits no more drops its clock. A pass
in which `jmerge` failed, or that could not list the threads, counts nothing and keeps the clocks.
A crew that waits on a usage limit (`Pass.limited`) or on a gate is left to `failover` and the
gate. The outbox holds each line `_send` has for a thread on a capped instance (`jbus.outbox`), so
the one try waits for the reset, and the count stops at `PASSES` while it waits. Where another step
of jbus nudges the crew about the same head just as the clock is due (an expedite the outbox held
until the reset), the clock starts again, so the reviewer is not asked twice at once. A thread that
ended with no Result and no pull request is `threads.resume`'s.

`held` watches the waits no clock above takes, by their reason. Rows whose pull requests `jmerge`
holds on one reason, with no thread at work on the cause, wake the home that owns them once the
hold is older than `HOLD_MINUTES`, once for the hold, with the reason, the rows and how long they
have been held. A thread is at work on the cause when it is a held row's crew or reviewer, when
the reason names its slug, or when it is a fix row of a red main (`mainjson.fix_of`) and the reason
is that red. A wait on the merge runner (`RUNNER`), a wait on a row ahead (`AHEAD`) whose pull
request is open, since that row's own wait is what holds it, a hold that is the user's (step
`hold`, already on what waits on the user) and a wait with its own clock above are no such hold.
A required check with no run at the head (`ready.NO_RUN`) is no wait on the merge runner: no
runner is at work on it, so it is a hold. One whose workflow GitHub runs there (`ready.LIVE_RUN`)
is such a wait.
A row ahead with no open pull request, closed with no merge or not opened yet, holds its rows
with nothing watching it, so that wait is a hold. `held.json`
keeps each hold, from the first pass that saw it with nobody at work: a pass with a thread at work
on it, or in which no row waits on it, drops it, and the next one starts afresh. From the wake
on, `waiting.keep` lists the hold on what waits on the user (`waiting.held`).
"""

from __future__ import annotations

import hashlib
import re
import string
from datetime import datetime
from typing import Any

import jbus
from jbriefs import below, findings
from jbriefs.home import home_of
from jbus import (
    dispatch,
    expedite,
    merge,
    outbox,
    read_json,
    rebase,
    threads,
    verbs,
    watch,
    write_json,
)
from jbus.passes import Pass
from jbus.review import FIXES, class_of, matches
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, task_brief
from jmerge import mainjson, ready

HELD = "hold-stall"
EVENTS = {"clock": "quiet", "hold-stall": "quiet"}
CLOCK = "clock"
STALL = "stall"
FILE = "clock.json"
PASSES = 10
AT_WORK = ("moving", "quiet", "waiting")
CARRY_ON = (
    "jbus: pull request #{number} of this task has waited {passes} passes on you, with your "
    "thread not at work: {reason}. Carry on with your brief from where you stopped: read "
    "`tasks/{slug}.md` and your worktree's `git status` and `git log` first, keep what is "
    "committed, do not start over, and do what the crew skill says next for your pull request."
)
ROOTED = (
    "jbus: your scoped reviewer {reviewer} of pull request #{number} has no worktree: it runs in "
    "the project's main checkout and refuses there, so jbus sends it its line no more. Launch a "
    "new scoped reviewer in {worktree}, with `workspaceStrategy` `existing_worktree` on that "
    "worktree and the message `{line}`, and put its id on the `Scoped reviewer:` line in place of "
    "{reviewer}."
)
"""What the crew is told, once per head, of a scoped reviewer that T3 Code says has no
worktree, in place of sending that reviewer its line again."""
HOLD_MINUTES = 30
"""The minutes rows may be held by one reason with no thread at work on it before jbus wakes their
home and lists the hold on what waits on the user."""
HELD_FILE = "held.json"
RUNNER = (
    ready.MAIN_MOVED,
    ready.UNDECIDED,
    ready.NOT_PASSED,
    ready.LIVE_RUN,
    ready.MIGRATION_MERGING,
    ready.BASE_MERGE_ASKED,
    ready.BASE_MERGE_DUE,
    ready.BASE_MOVED_ASKED,
    ready.BASE_MOVED_DUE,
)
"""The waits the merge runner is at work on: `jmerge`, its gate, GitHub's merge of the base, and
CI."""
AHEAD = (
    (ready.MERGES_AFTER, "slug"),
    (ready.STACKED_ON, "slug"),
    (ready.CARRIES_AFTER, "slug"),
    (ready.MIGRATION_REBASING, "number"),
)
"""The waits on a row ahead, each with the field that names that row. While its pull request is
open, what holds it is its own wait, which the merge runner, a thread, `held` or a clock above is
on, so the rows behind it are no hold of their own."""
HELD_HOME = (
    "jbus: {rows} of this home's have been held {minutes} minutes by one reason, {reason}, and "
    "no thread is at work on it. Nobody picks it up by itself: pick it up as the home skill's "
    '"Picking up a thread that stopped" says, or brief its fix. It is on what waits on the user '
    "until it clears or a thread takes it up."
)
_SEAT = re.compile(r"#(\d+)$")


def _id(said: str) -> str:
    """Return the thread a reviewer line names after its label, or nothing for `none`."""
    found = "".join(said.split()[:1]).rstrip(",")
    return "" if found == "none" else found


def reviewer(brief: str, kind: str, reason: str, head: str) -> str:
    """Return the thread of the reviewer that a wait is for, or nothing where the brief names none.

    For a scoped wait it is the last `Scoped reviewer:` line of this head, or else the last one.
    For a second review it is the last `Second reviewer:` line. Otherwise it is the last
    `Reviewer:` line whose seat, `#<n>`, has written no `## Review` with that seat on its `By:`
    line."""
    if kind == "scoped":
        named = below.reviewers(brief, "Scoped reviewer", head)
        named = named or below.reviewers(brief, "Scoped reviewer")
    elif "second" in reason:
        named = below.reviewers(brief, "Second reviewer")
    else:
        bys = (_SEAT.search(one.by) for one in findings.triage(brief).sections)
        wrote = {seat[1] for seat in bys if seat}
        named = below.reviewers(brief, "Reviewer")
        named = [said for said in named if (s := _SEAT.search(said)) is None or s[1] not in wrote]
    return next((found for found in map(_id, reversed(named)) if found), "")


def _ask(run: Pass, slug: str, kind: str, reason: str, head: str, brief: str) -> tuple[str, str]:
    """Return the thread a wait is on and the line jbus sends it: the reviewer's line, or nothing
    where the crew is the one to carry on."""
    if kind == "result":
        return jbus.thread_of(run.home, slug), ""
    named = reviewer(brief, kind, reason, head)
    if not named and kind == "review" and expedite.no_reviewer_by_rule(brief, head):
        return "", ""
    if not named:
        return jbus.thread_of(run.home, slug), ""
    if kind == "review":
        return named, expedite.AGAIN.format(slug=slug)
    found = expedite.ranges(run, slug, head, "fix" if matches(reason, FIXES) else "rebase")
    if not found:
        return jbus.thread_of(run.home, slug), ""
    return named, expedite.SCOPED.format(slug=slug, old=found[0], new=found[1])


def _send(
    run: Pass,
    client: Client,
    thread: str,
    message: str,
    key: str,
    who: str = "",
    *,
    needs: outbox.Needs,
) -> str:
    """Queue one message to a thread, once for the key. Return `sent`, or `refused` where T3 Code
    refused it, as it does for a thread that is gone, which no later pass would change, or nothing
    for a call that got no answer or a message the outbox holds, which the next pass tries again.
    `who` names what the line is about in a `wait` line, the slug of the key where it is not
    given."""
    who = who or key.split("|")[1]
    if key in run.box.sent():
        return "sent"
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=who,
            key=key,
            text=message,
            template=key.split("|")[0],
            needs=needs,
        )
    except T3Refused as error:
        run.say(f"wait {who}: T3 Code refused {thread} its clock's line ({error})")
        run.box.mark(key)
        return "refused"
    except T3Error as error:
        run.say(f"wait {who}: {thread} could not be sent its clock's line ({error})")
        return ""
    if not went:
        return ""
    run.box.mark(key)
    return "sent"


def _act(run: Pass, client: Client, slug: str, wait: dict[str, Any]) -> bool:
    """Send the thread a wait is on its line or a carry-on, once. Return whether it went."""
    number, reason, line = wait["number"], wait["reason"], wait["line"]
    key = f"{CLOCK}|{slug}|{wait['kind']} {wait['head'][:12]} {wait['thread']}"
    thread, did = wait["thread"], "relaunched its reviewer" if line else "carried its crew on"
    crew = jbus.thread_of(run.home, slug)
    if wait["kind"] == "scoped" and line and crew and rebase.worktree(client, thread) is None:
        there = rebase.where(client, crew)
        line = ROOTED.format(reviewer=thread, number=number, worktree=there, line=line)
        key, thread = f"{CLOCK}|{slug}|rooted {wait['head'][:12]}", crew
        did = "told its crew to launch its scoped reviewer in its worktree"
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
    went = _send(run, client, thread, line, key, needs="act")
    if not went:
        return False
    wait["did"] = did
    did += ", and T3 Code refused it" if went == "refused" else ""
    said = f"{CLOCK} {slug}: #{number} waited {wait['passes']} passes on {reason}; {did}"
    run.find(slug, CLOCK, f"{said}, {thread}", line, key=key.split("|", 2)[2])
    run.say(f"{said}, {thread}")
    return True


def _home(run: Pass, slug: str, wait: dict[str, Any], brief: str) -> None:
    """Log one quiet stall of a wait jbus acted on that still waits. The stall is an item of the
    one list, which takes it to the brief's home, or to the root home where it has none
    (`jbus.wakes`)."""
    did = wait.get("did") or ("relaunched its reviewer" if wait["line"] else "carried its crew on")
    crew = jbus.thread_of(run.home, slug) or "not known"
    home = jbus.thread_of(home_of(run.home, brief))
    why = "it is its home's from here" if home else "it has no home to tell"
    key = f"{wait['kind']} {wait['head'][:12]} {wait['thread']}"
    line = f"{STALL} {slug}: #{wait['number']} waited {wait['passes']} passes after jbus {did}"
    line += f", {wait['reason']}, with {wait['thread']} not at work, and {why}"
    run.find(slug, STALL, f"{line}; its crew's thread is {crew}", key=f"{CLOCK} {key}")


def _nudges(run: Pass, slug: str, head: str) -> int:
    """Count the messages jbus's other steps sent about the slug at this head (`expedite`'s keys
    name both)."""
    keys = (key.split("|") for key in run.box.sent() if not key.startswith(CLOCK))
    return sum(1 for key in keys if key[1:3] == [slug, head[:12]])


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
        brief = task_brief(run, slug)
        thread, line = _ask(run, slug, kind, reason, head, brief)
        if not thread:
            continue
        seen = was.get(slug, {})
        same = (seen.get("kind"), seen.get("head"), seen.get("thread")) == (kind, head, thread)
        wait = seen if same else {"passes": 0, "acted": False, "home": False}
        wait = {**wait, "kind": kind, "head": head, "thread": thread, "line": line}
        wait |= {"number": pull["number"], "reason": reason}
        kept[slug] = wait
        busy = {live.get(thread), live.get(jbus.thread_of(run.home, slug))} & set(AT_WORK)
        if wait["home"] or busy or slug in reviewing:
            continue
        nudges = _nudges(run, slug, head)
        grew, wait["nudges"] = nudges > wait.get("nudges", nudges), nudges
        if wait["passes"] + 1 >= PASSES and grew:
            wait["passes"] = 0
            continue
        wait["passes"] = min(wait["passes"] + 1, PASSES)
        if wait["passes"] < PASSES:
            continue
        if not wait["acted"] and _act(run, client, slug, wait):
            wait |= {"acted": True, "passes": 0}
        elif wait["acted"]:
            _home(run, slug, wait, brief)
            wait["home"] = True
    if kept != was:
        write_json(run.state / FILE, kept)


def _ahead(reason: str, world: World) -> bool:
    """Say whether the reason is a wait on a row ahead whose pull request is open."""
    numbers = {str(pull["number"]) for pull in world.open.values()}
    for one, field in AHEAD:
        pattern = "".join(
            re.escape(literal) + ("" if name is None else "(.+?)" if name == field else ".+")
            for literal, name, _, _ in string.Formatter().parse(one)
        )
        if found := re.fullmatch(pattern, reason):
            return found[1] in (world.open if field == "slug" else numbers)
    return False


def _on(slug: str, reason: str, rows: list[str]) -> bool:
    """Say whether a thread of the slug works on what holds the rows: it is one of theirs, the
    reason names it, or it is the fix of the red main the reason names."""
    if slug in rows or slug in re.findall(r"[\w.-]+", reason):
        return True
    return mainjson.fix_of(slug) and bool(re.fullmatch(ready.MAIN_RED.pattern, reason))


def held(
    run: Pass, client: Client, world: World, pulls: merge.Said, out: list[dict[str, Any]] | None
) -> None:
    """Keep each hold nobody works on, and wake its home once it is due. See the module."""
    waits = watch.waits(pulls)
    if waits.failed or out is None:
        return
    was: dict[str, Any] = read_json(run.state / HELD_FILE, {})
    groups: dict[str, dict[str, Any]] = {}
    for slug, pull in sorted(world.open.items(), key=lambda one: one[1]["number"]):
        word, _, reason = waits.said.get(str(pull["number"]), "").partition(": ")
        if word != "wait" or not reason or class_of(reason) or matches(reason, RUNNER):
            continue
        if _ahead(reason, world):
            continue
        scope = home_of(run.home, task_brief(run, slug))
        name = "" if scope == run.home else scope.name
        key = hashlib.sha256(f"{name}\n{reason}".encode()).hexdigest()[:12]
        group = groups.setdefault(key, {"reason": reason, "home": name, "rows": [], "numbers": []})
        group["rows"].append(slug)
        group["numbers"].append(pull["number"])
    busy = [one["slug"] for one in out if one.get("live") in AT_WORK and one.get("slug")]
    kept: dict[str, Any] = {}
    for key, group in groups.items():
        if any(_on(slug, group["reason"], group["rows"]) for slug in busy):
            continue
        hold = {"since": run.now.isoformat(), "woke": False} | was.get(key, {}) | group
        minutes = int((run.now - datetime.fromisoformat(hold["since"])).total_seconds() // 60)
        hold["minutes"] = minutes
        kept[key] = hold
        if hold["woke"] or minutes <= HOLD_MINUTES:
            continue
        pairs = zip(hold["rows"], hold["numbers"], strict=True)
        rows = ", ".join(f"{slug} (#{number})" for slug, number in pairs)
        text = HELD_HOME.format(rows=rows, minutes=minutes, reason=hold["reason"])
        at = jbus.thread_of(run.home / hold["home"])
        sending = f"{HELD}|{key}|{hold['since']}"
        went = _send(run, client, at, text, sending, rows, needs="decide") if at else "no home"
        if not went:
            continue
        hold["woke"] = True
        to = f"told its home, thread {at}" if went == "sent" else f"{went}, told nobody"
        said = f"{HELD} {run.project.name}: {rows} held {minutes} minutes by {hold['reason']}; {to}"
        run.find("", HELD, said, key=f"{key} {hold['since']}")
        run.say(said)
    if kept != was:
        write_json(run.state / HELD_FILE, kept)


STEPS = (
    verbs.Step(
        "after-expedite",
        16,
        "clock.held",
        lambda half: held(half.run, half.client, half.seen.world, half.said, half.out),
        ("client", "world"),
    ),
    verbs.Step(
        "after-expedite",
        15,
        "clock.tick",
        lambda half: tick(half.run, half.client, half.seen.world, half.said, half.out),
        ("client", "world"),
    ),
)
