"""Every wait on the system has a clock: a pull request that waits on a reviewer that never writes,
or on a crew that stopped, is asked again by how long it has waited, not by how often `jmerge`
repeats its line.

`tick` reads what jbus's own run of `jmerge` says in this pass of each open pull request that jbus
launched a crew for, and sorts the wait into one of three classes:

- `review`: the review is not written (`it has no review yet`, `its review has no verdict`), or
  a reviewer jbus launched before the pull request opened has not written (`jbus.prereview`),
  a wait numbered 0, since no pull request is open yet;
- `scoped`: the scoped review a `Meets the brief: no` owes, or a rebase's, is not written or has
  not ruled;
- `result`: no Result names the pull request, so the crew stopped before it wrote one.

A fourth class, `check`, is read from GitHub and not from `jmerge`: a required check failed at the
pull request's head, and `jbus.stall.twice` counted that head as the row's own red (`fails.json`),
so a head whose check ran on main's red tip (`main.json`'s `broken`) or failed only on a shared
flake (`reverts.flaky`) is none. It waits on the crew, and acts at once instead of at `PASSES`, see
below. While a row has one, it is the row's wait, and `held` leaves its pull request to it.

Each wait has one thread it waits on. For `review` and `scoped` that is the reviewer the brief's
last `Reviewer:` or `Scoped reviewer:` line names, and the crew where the brief
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

A `check` wait has no pass count. Its first word is `jbus.rebase`'s fix message for the head (or
its rebase message), which goes as today. After it, each idle spell of the crew at that head gets
one `RESTART`, on the first pass of the spell: it names the pull request, the head and each failed
job with its log link. A spell starts on a pass that finds the crew's thread not at work (its turn
ended, no pending request) after the last word went, once T3 Code saw the thread at work since,
or its item count moved. A spell gets one restart however many passes it lasts. After `RESTARTS`
restarts at one head with nothing pushed, the next spell is one quiet `stall` for the home, as
for the other classes. A push is a new head, and so a new wait. A row held in the queue (`jbus
queue hold`, or `check failed twice`) has no `check` wait, and the outbox holds a restart as it
holds any fix message (`outbox.FIXES`) and any line to a capped instance.

`held` watches the waits no clock above takes, by their reason. Rows whose pull requests `jmerge`
holds on one reason, with no thread at work on the cause, wake the home that owns them once the
hold is older than `HOLD_MINUTES`, once for the hold, with the reason, the rows and how long they
have been held. A thread is at work on the cause when the reason's code is a crew's (`BOUNDS`) and
the thread is a held row's crew or reviewer, or the reason names its slug. A thread at work on a
code a crew cannot clear, as a run GitHub keeps queued (`ready.NO_RUN`), is at work on something
else, so it keeps no hold from waking the home. A wait on the merge runner (`RUNNER`), a wait
on a row ahead (`AHEAD`) whose pull request is open, since that row's own wait is what holds it, a
hold that is the user's (a `wait` or `hold` on step `hold`, such as a queue row held for `check
failed twice`, which `waiting.holds` lists from its first pass) and a wait with its own clock
above are no such hold.
A required check with no run at the head (`ready.NO_RUN`) is no wait on the merge runner: no
runner is at work on it, so it is a hold. One whose workflow GitHub runs there (`ready.LIVE_RUN`)
is such a wait.
A row ahead with no open pull request, closed with no merge or not opened yet, holds its rows
with nothing watching it, so that wait is a hold. `held.json` keeps each hold, from the first pass
that saw it with nobody at work on its cause: a pass with a thread at work on its cause, or in
which no row waits on it, drops it, and the next one starts afresh. From the wake on,
`waiting.keep` lists the hold on what waits on the user (`waiting.held`).

Each hold in `held.json` names who owns it, `who`. It is `crew` where `expedite.tell` owns the wait
of every row it holds: a row of `expedite.TABLE` that `tell` counts at the row's head and has not
given to the user (`_tells_left`). It is `user` for the rest. A `crew` hold wakes the home
only once `tell` has sent each row every message it owes at that head, two for a `proved-` or
`checked-` wait, and the hold is older than `HOLD_MINUTES` with nobody at work on it after that.

Each code of `jmerge`'s reasons (`ready.Reason`) has one row of `BOUNDS`: its owner, the one who
clears it, and its bound, the minutes a row may wait on it with its `why` unchanged. The owner is
a jbus act (`ACT`: jbus, `jmerge` or GitHub are at work on it, as on a run in CI or a run GitHub
kept queued), the row's crew or reviewer (`CREW`, or the crew of the row ahead the reason names),
the row's home (`HOME`: nothing at work moves it), or the user (`USER`: a code on the `hold` step,
which `waiting.holds` lists for the user from its first pass, so it has no bound here). `held`
reads the owner: a thread at work drops a hold only where its code is a crew's, since a busy crew
starts no run GitHub keeps queued.

`aged` is the backstop over every remedy: a row whose `why`, a `wait` of `jmerge`'s, is unchanged
past its code's bound, read with its `since` from `waits.jsonl`, is aged, whoever owns the code
and whatever step was meant to clear it. It is a guard by design, for a state no step has a remedy
for: each remedy stays the act of its own module (`cancelled`, `rebase`, `expedite`, the clocks
above), and `aged` only escalates what none of them moved. `jbus clear` prints an aged row as its
home's `fix wait:<slug>`, and as a decision once the home's fixes of it reach `retry_cap`
(`jbus.blockers`), and the view lists it as an `aged` wrong (`jbus.view.state.wrongs`).

A `user` hold that a word of the user's lifts (`judgement.accepted`: `jmerge --accept`) names that
word as its `lift`. Its crew had its turns and gave it to the user (`expedite.tell`), or no crew of
jbus's has it, so nothing but that word moves it: it is listed on what waits on the user in the
pass that files it, with no `HOLD_MINUTES` to wait and no wake of the home, which hears of it from
that list. `jbus needs` lists it with the word (`blockers.needs`), and `work.json` says its rows
wait on the user (`lifted`).
"""

from __future__ import annotations

import hashlib
import re
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jbriefs import below, findings, reviewers
from jbriefs.home import home_of, thread_of
from jbus import (
    END_TURN,
    crewthread,
    dispatch,
    expedite,
    merge,
    mirror,
    outbox,
    queue,
    read_json,
    rebase,
    review,
    threads,
    verbs,
    watch,
    work,
    write_json,
)
from jbus.passes import Pass
from jbus.review import FIXES, class_of, matches
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, task_brief
from jmerge import judgement, ready
from jmerge.checks import check_state, latest_of_each
from jmerge.judgement import step

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
RESTART = (
    "jbus: {checks} failed on your pull request #{number} at {short}, and your thread stopped "
    "with nothing pushed. The failed jobs: {jobs}. Carry on from where you stopped: read "
    "`tasks/{slug}.md` and your worktree's `git status` and `git log` first, keep what is "
    'committed, then run the block of "The checks" in your own worktree and do what it prints. '
    "{end}"
)
"""What the crew is told, once per idle spell, of a required check that failed at its head."""
RESTARTS = 2
"""The restarts at one head a crew gets before its next idle spell goes to its home."""
RESTARTED = "restart"
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
    ready.QUEUED_RESTARTED,
    ready.QUEUED_UNOPENED,
    ready.QUEUED_UNCLOSED,
)
"""The waits the merge runner is at work on: `jmerge`, its gate, GitHub's merge of the base, CI,
and the one restart of a run GitHub kept queued at the head of the line, with the close or the
reopen `jmerge` tries again for `ready.RESTART_MINUTES`. A run still queued after that restart
(`ready.QUEUED_GAVE_UP`), a restart that never took (`ready.QUEUED_UNRESTARTED`) and a reopen
`jmerge` asks no more (`ready.QUEUED_UNREOPENED`) are holds: nothing at work moves them."""
AHEAD = (
    (ready.MERGES_AFTER, "slug"),
    (ready.STACKED_ON, "slug"),
    (ready.CARRIES_AFTER, "slug"),
    (ready.MIGRATION_REBASING, "number"),
    (ready.IN_LINE, "number"),
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
ACT, CREW, HOME, USER = "jbus act", "crew", "home", "user"
OWNERS = (ACT, CREW, HOME, USER)
"""Who clears a wait: see the module."""


@dataclass(frozen=True)
class Bound:
    """Who clears a wait on one code, and the minutes it may stand unchanged before it is aged,
    or None for a code the user's list carries from its first pass."""

    owner: str
    minutes: int | None


ACT_MINUTES = 60
"""Two of `jmerge`'s `QUEUED_MINUTES`: time for a run to start, and for one restart of it."""
CREW_MINUTES = 120
"""Time for the clocks above to ask the thread twice and give its stall to the home."""
AHEAD_MINUTES = 240
"""A wait on a row ahead: that row's own wait ages first, and these rows only if it does not."""
_CODES: tuple[tuple[str, int | None, tuple[str, ...]], ...] = (
    (
        ACT,
        ACT_MINUTES,
        tuple(
            one.code
            for one in (
                ready.MAIN_MOVED,
                ready.MERGE_FAILED,
                ready.NO_MESSAGES,
                ready.NOT_PASSED,
                ready.NO_RUN,
                ready.CANCELLED_UNRUN,
                ready.LIVE_RUN,
                ready.UNDECIDED,
                ready.MAIN_CHANGED,
                ready.CARRIES_UNKNOWN,
                ready.MIGRATION_MERGING,
                ready.BASE_MERGE_ASKED,
                ready.BASE_MERGE_DUE,
                ready.BASE_MOVED_ASKED,
                ready.BASE_MOVED_DUE,
                ready.QUEUED_RESTARTED,
                ready.QUEUED_UNOPENED,
                ready.QUEUED_UNCLOSED,
                ready.MERGED_TREE_UNENDED,
                ready.MERGED_TREE_UNBUILT,
                ready.MERGED_TREE_NO_TIME,
                ready.MERGED_TREE_NO_SLOT,
                ready.MERGING,
                ready.IN_BATCH,
                ready.BATCH_FIRST,
                ready.BATCH_STOPPED,
                ready.MAIN_BROWSER_RED,
            )
        )
        + tuple(code for code, _, _ in ready.ELSEWHERE),
    ),
    (
        CREW,
        CREW_MINUTES,
        tuple(
            one.code
            for one in (
                ready.NO_BRIEF,
                ready.HAND_DRAFT,
                ready.FRESH_CONFLICT,
                ready.NO_HEAD,
                ready.BASE,
                ready.NO_REVIEW,
                ready.SKILLS_UNRUN,
                ready.PROVED_MISSING,
                ready.PROVED_UNREAD,
                ready.PROVED_NOT_EXEMPT,
                ready.PROVED_NOT_KIND,
                ready.PROVED_UNNAMED,
                ready.PROVED_BASE_PASSED,
                ready.PROVED_HEAD_FAILED,
                ready.PROVED_STALE,
                ready.CHECKED_MISSING,
                ready.CHECKED_STALE,
                ready.CHECKED_CUT,
                ready.CHECKED_FAILED,
                ready.CHECKED_PART,
                ready.NO_VERDICT,
                ready.NO_FIXED,
                ready.NOT_PUSHED,
                ready.FIX_UNREVIEWED,
                ready.DECLINES_OVERRULED,
                ready.MEETS_NO,
                ready.MEETS_UNREAD,
                ready.MEETS_MISCOUNTED,
                ready.UNENDED,
                ready.UNANSWERED,
                ready.UNPROVEN,
                ready.UNCITED,
                ready.REPEATED,
                ready.RISK_UNASKED,
                ready.CANNOT_CHECK,
                ready.DROPPED,
                ready.SCOPED_UNRULED,
                ready.CONTENT_CHANGED,
                ready.CHECK_FAILED,
                ready.CONFLICTS,
                ready.STACKED_UNMOVED,
                ready.MIGRATION_TAKEN,
                ready.UNMERGED,
                ready.MERGED_TREE_FAILS,
                ready.BROWSER_RED,
            )
        ),
    ),
    (CREW, AHEAD_MINUTES, tuple(one.code for one, _ in AHEAD)),
    (
        HOME,
        HOLD_MINUTES,
        (
            *(
                one.code
                for one in (
                    ready.OTHER_HOME,
                    ready.CANCELLED_TWICE,
                    ready.BASE_MERGE_REFUSED,
                    ready.QUEUE_UNREADABLE,
                    ready.QUEUED_GAVE_UP,
                    ready.QUEUED_UNRESTARTED,
                    ready.QUEUED_UNREOPENED,
                )
            ),
            ready.UNKNOWN,
        ),
    ),
    (USER, None, tuple(one.code for one in ready.reasons().values() if one.step == "hold")),
)


def _bounds() -> dict[str, Bound]:
    """`_CODES` by code. A code on two rows is a slip, and stops the import."""
    found: dict[str, Bound] = {}
    for owner, minutes, codes in _CODES:
        for code in codes:
            if code in found:
                raise ValueError(f"{code} has two rows of clock.BOUNDS")
            found[code] = Bound(owner, minutes)
    return found


BOUNDS = _bounds()
"""Each code of `jmerge`'s reasons, its owner and its bound: see the module. A code `jmerge`
gains with no row here fails `test_jbus_held_aged`."""


def bound(reason: str) -> Bound:
    """The row of `BOUNDS` of a reason `jmerge` gives, by its code (`ready.code_of`)."""
    return BOUNDS.get(ready.code_of(reason)) or BOUNDS[ready.UNKNOWN]


@dataclass(frozen=True)
class Aged:
    """A row whose wait is unchanged past its code's bound: its reason, the row of `BOUNDS`, and
    since when it has waited on it, from `waits.jsonl`."""

    slug: str
    reason: str
    bound: Bound
    since: datetime
    minutes: int

    @property
    def said(self) -> str:
        """The wait as a blocker says it."""
        return (
            f"it has waited {self.minutes} minutes on {self.reason}, past its bound of "
            f"{self.bound.minutes}, and the {self.bound.owner} that clears it has not"
        )


def aged(rows: list[queue.Row], waits: list[dict[str, Any]], now: datetime) -> dict[str, Aged]:
    """By slug, each open row whose `why` is a `wait` of `jmerge`'s that has not changed past its
    code's bound. Its `since` is the `at` of the row's last line of `waits.jsonl` (`waits`), which
    the pass writes before the table: a row whose last line is not its `why` has no known `since`,
    and is not aged. A code of the user's (`USER`) is never aged here. It reads only what it is
    given, so `jbus clear` and the view read the same rows the same way."""
    last: dict[str, dict[str, Any]] = {}
    for one in waits:
        if isinstance(one, dict) and isinstance(one.get("slug"), str):
            last[one["slug"]] = one
    found = {}
    for row in rows:
        why, slug = str(row.get("why") or ""), row["slug"]
        word, _, reason = why.partition(": ")
        line = last.get(slug) or {}
        if work.over(row) or word != "wait" or not reason or line.get("why") != why:
            continue
        rule = bound(reason)
        try:
            since = datetime.fromisoformat(str(line.get("at")))
        except ValueError:
            continue
        minutes = int((now - since).total_seconds() // 60)
        if rule.minutes is not None and minutes >= rule.minutes:
            found[slug] = Aged(slug, reason, rule, since, minutes)
    return found


def _id(said: str) -> str:
    """Return the thread a reviewer line names after its label, or nothing for `none`."""
    found = "".join(said.split()[:1]).rstrip(",")
    return "" if found == "none" else found


def reviewer(brief: str, kind: str, reason: str, head: str) -> str:
    """Return the thread of the reviewer that a wait is for, or nothing where the brief names none.

    For a scoped wait it is the last `Scoped reviewer:` line of this head, or else the last one.
    Otherwise it is the last
    `Reviewer:` line whose seat, `#<n>`, has written no `## Review` that ran with that seat on
    its `By:` line: a `Verdict: not run` section leaves its seat to be asked again."""
    if kind == "scoped":
        named = below.reviewers(brief, "Scoped reviewer", head)
        named = named or below.reviewers(brief, "Scoped reviewer")
    else:
        bys = (_SEAT.search(one.by) for one in findings.triage(brief).sections if one.ran)
        wrote = {seat[1] for seat in bys if seat}
        named = below.reviewers(brief, "Reviewer")
        named = [said for said in named if (s := _SEAT.search(said)) is None or s[1] not in wrote]
    return next((found for found in map(_id, reversed(named)) if found), "")


def _ask(run: Pass, slug: str, kind: str, reason: str, head: str, brief: str) -> tuple[str, str]:
    """Return the thread a wait is on and the line jbus sends it: the reviewer's line, or nothing
    where the crew is the one to carry on."""
    if kind == "result":
        return crewthread.crew(run, slug), ""
    named = reviewer(brief, kind, reason, head)
    if not named and kind == "review" and expedite.no_reviewer_by_rule(brief, head):
        return "", ""
    if not named:
        return crewthread.crew(run, slug), ""
    if kind == "review":
        return named, expedite.AGAIN.format(slug=slug)
    found = review.ranges(run, slug, head, "fix" if matches(reason, FIXES) else "rebase", brief)
    if not found:
        return crewthread.crew(run, slug), ""
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
    crew = crewthread.crew(run, slug)
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
    one list, which takes it to the brief's home, or to the user's band where that home has no
    thread (`jbus.view.state.owner`)."""
    did = wait.get("did") or ("relaunched its reviewer" if wait["line"] else "carried its crew on")
    crew = crewthread.crew(run, slug) or "not known"
    home = thread_of(home_of(run.home, brief))
    why = "it is its home's from here" if home else "it has no home to tell"
    key = f"{wait['kind']} {wait['head'][:12]} {wait['thread']}"
    if wait["kind"] == "check":
        waited = f"is red on {wait['head'][:12]} after jbus restarted its crew {RESTARTS} times"
    else:
        waited = f"waited {wait['passes']} passes after jbus {did}"
    line = f"{STALL} {slug}: #{wait['number']} {waited}"
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
    kept = _checks(run, client, world, out, was)
    for slug, number, reason, head in _waiting(run, world, waits.said):
        if slug in kept:
            continue
        kind = class_of(reason)
        if not kind or not head:
            continue
        if not dispatch.launched(run, slug) or slug in run.limited or slug in run.gated:
            continue
        brief = task_brief(run, slug)
        thread, line = _ask(run, slug, kind, reason, head, brief)
        if not thread:
            continue
        seen = was.get(slug, {})
        same = (seen.get("kind"), seen.get("head"), seen.get("thread")) == (kind, head, thread)
        wait: dict[str, Any] = seen if same else {"passes": 0, "acted": False, "home": False}
        wait = {**wait, "kind": kind, "head": head, "thread": thread, "line": line}
        wait |= {"number": number, "reason": reason}
        kept[slug] = wait
        busy = {live.get(thread), live.get(crewthread.crew(run, slug))} & set(AT_WORK)
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


def _red(run: Pass, world: World, slug: str, pull: dict[str, Any]) -> list[tuple[str, str]]:
    """Return each required check that failed at the pull request's head, with its log link, where
    `jbus.stall.twice` counted the head as the row's own red, or nothing."""
    head = str(pull.get("headRefOid") or "")
    kept = read_json(run.state / watch.FAILS, {})
    one = kept.get(slug) if isinstance(kept, dict) else None
    counted = ((one or {}).get("heads") or {}).get(head) if isinstance(one, dict) else None
    if not head or not isinstance(counted, dict):
        return []
    names = set(counted.get("checks") or ())
    never = frozenset(pull.get(watch.NEVER) or ())
    return [
        (str(check.get("name") or check.get("context")), str(check.get("detailsUrl") or ""))
        for check in latest_of_each(pull.get("statusCheckRollup") or [])
        if (check.get("name") or check.get("context")) in names
        and check_state(check, never) == "failed"
    ]


def _told(run: Pass, slug: str, head: str) -> bool:
    """Say whether `jbus.rebase` gave the crew its word on this head: the fix message of its failed
    check, or of a rerun, or the rebase that stands in for both."""
    sent = run.box.sent()
    return any(rebase.mark(kind, slug, head) in sent for kind in ("failed", "refailed", "rebase"))


def _checks(
    run: Pass, client: Client, world: World, out: list[dict[str, Any]], was: dict[str, Any]
) -> dict[str, Any]:
    """Keep each `check` wait, and restart a crew whose idle spell is new. See the module."""
    seen = {one["id"]: one for one in out}
    kept: dict[str, Any] = {}
    for slug, pull in sorted(world.open.items()):
        crew, head = crewthread.crew(run, slug), str(pull.get("headRefOid") or "")
        if not dispatch.launched(run, slug) or slug in run.limited or slug in run.gated:
            continue
        jobs = _red(run, world, slug, pull)
        if not jobs or (queue.fresh(run.state, slug) or {}).get("held"):
            continue
        reason = f"{', '.join(dict.fromkeys(name for name, _ in jobs))} failed"
        before = was.get(slug, {})
        same = [before.get(field) for field in ("kind", "head", "thread")] == ["check", head, crew]
        wait: dict[str, Any] = before if same else {"restarts": 0, "worked": False, "home": False}
        wait = {**wait, "kind": "check", "head": head, "thread": crew, "line": RESTARTED}
        wait |= {"number": pull["number"], "reason": reason, "passes": 0}
        kept[slug] = wait
        thread = seen.get(crew, {})
        items = thread.get("items")
        if wait["home"]:
            continue
        if thread.get("live") in AT_WORK:
            wait["worked"] = True
            continue
        if not _told(run, slug, head):
            wait |= {"items": items, "worked": False}
            continue
        moved = items is not None and wait.get("items") not in (None, items)
        if "items" in wait and not wait["worked"] and not moved:
            continue
        if wait["restarts"] >= RESTARTS:
            _home(run, slug, wait, task_brief(run, slug))
            wait["home"] = True
            continue
        if _restart(run, client, slug, wait, jobs):
            wait |= {"restarts": wait["restarts"] + 1, "items": items, "worked": False}
    return kept


def _restart(
    run: Pass, client: Client, slug: str, wait: dict[str, Any], jobs: list[tuple[str, str]]
) -> bool:
    """Send the crew one restart for its idle spell at the head. Return whether it went."""
    head, number, n = wait["head"], wait["number"], wait["restarts"] + 1
    named = "; ".join(f"{name}, {link}" if link else name for name, link in jobs)
    text = threads.resume_message(
        RESTART,
        f"crew: {slug}",
        run.home,
        checks=", ".join(dict.fromkeys(name for name, _ in jobs)),
        number=number,
        short=head[:12],
        jobs=named,
        slug=slug,
        end=END_TURN,
    )
    key = f"{RESTARTED}|{slug}|{head[:12]} {n}"
    went = _send(run, client, wait["thread"], text, key, needs="act")
    if not went:
        return False
    did = f"restarted its crew ({n} of {RESTARTS})"
    did += ", and T3 Code refused it" if went == "refused" else ""
    said = f"{CLOCK} {slug}: #{number} is red on {head[:12]}, {wait['reason']}; {did}"
    run.find(slug, CLOCK, f"{said}, {wait['thread']}", text, key=key.split("|", 2)[2])
    run.say(f"{said}, {wait['thread']}")
    wait["did"] = "restarted its crew"
    return True


def _waiting(run: Pass, world: World, said: dict[str, str]) -> list[tuple[str, int, str, str]]:
    """Each wait a clock takes: the slug, the pull request's number, `jmerge`'s reason and the
    head, for each open pull request `jmerge` says waits; and for each row whose review comes
    before its pull request (`review.awaited`) and whose reviewer jbus launched has not written,
    a wait on the review at the head its desk proof names, numbered 0, since no pull request is
    open yet."""
    found = []
    for slug, pull in sorted(world.open.items()):
        word, _, reason = said.get(str(pull["number"]), "").partition(": ")
        if word == "wait":
            found.append((slug, pull["number"], reason, pull.get("headRefOid", "")))
    for slug in sorted(world.threads):
        if slug in world.open or slug in world.merged:
            continue
        brief = task_brief(run, slug)
        result = mirror.last_result(brief)
        if review.awaited(brief, result) and reviewers.launched(brief):
            found.append((slug, 0, str(ready.NO_VERDICT), review.desk_head(brief)))
    return found


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
    """Say whether a thread of the slug works on what holds the rows: it is one of theirs, or the
    reason names it."""
    return slug in rows or slug in re.findall(r"[\w.-]+", reason)


def _rows(run: Pass, world: World, said: dict[str, str]) -> list[tuple[str, int]]:
    """Each row with a pull request, and its number, by number: the open ones, and those whose
    brief names a pull request GitHub lists neither open nor merged that `jmerge` says a wait of,
    as it does while a restart of its queued run left it closed (`ready.QUEUED_UNREOPENED`)."""
    rows = [(slug, int(pull["number"])) for slug, pull in world.open.items()]
    numbers = {str(number) for _, number in rows}
    if any(number not in numbers for number in said):
        for url, slug in watch.tied(run).items():
            number = url.rstrip("/").rsplit("/", 1)[-1]
            if number in said and number not in numbers and slug not in world.merged:
                rows.append((slug, int(number)))
    return sorted(rows, key=lambda row: row[1])


def _tells_left(was: dict[str, Any], slug: str, number: int, reason: str) -> int | None:
    """Return how many messages `expedite.tell` still owes the crew about a wait at its head, from
    `expedite.json` as `was` holds it, or None where `tell` does not own the wait: no row of
    `expedite.TABLE` is its reason, `tell` keeps no count of it this pass, or it is the user's."""
    row = expedite.short_of(merge.Line("wait", number, "", reason))
    entry = was.get(slug)
    if row is None or not isinstance(entry, dict) or entry.get("users"):
        return None
    _, tells = row.spells or (expedite.AFTER, 1)
    return max(tells - entry.get("tells", 1 if "told" in entry else 0), 0)


def lifted(state: Path) -> frozenset[str]:
    """The rows of each hold `held` gave the user with the word that lifts it (`lift`): the rows
    `jbus needs` lists for it, and `work.json` says wait on the user."""
    kept: dict[str, Any] = read_json(state / HELD_FILE, {})
    return frozenset(
        slug
        for one in kept.values()
        if isinstance(one, dict) and one.get("woke") and one.get("lift")
        for slug in one.get("rows", [])
    )


def held(
    run: Pass, client: Client, world: World, pulls: merge.Said, out: list[dict[str, Any]] | None
) -> None:
    """Keep each hold nobody works on, and wake its home once it is due. See the module."""
    waits = watch.waits(pulls)
    if waits.failed or out is None:
        return
    was: dict[str, Any] = read_json(run.state / HELD_FILE, {})
    clocks: dict[str, Any] = read_json(run.state / FILE, {})
    told: dict[str, Any] = read_json(run.state / expedite.FILE, {})
    checked = {slug for slug, one in clocks.items() if one.get("kind") == "check"}
    groups: dict[str, dict[str, Any]] = {}
    owed: set[str] = set()
    for slug, number in _rows(run, world, waits.said):
        said = waits.said.get(str(number), "")
        word, _, reason = said.partition(": ")
        if slug in checked or step(said) == "hold":
            continue
        if word != "wait" or not reason or class_of(reason) or matches(reason, RUNNER):
            continue
        if _ahead(reason, world):
            continue
        scope = home_of(run.home, task_brief(run, slug))
        name = "" if scope == run.home else scope.name
        key = hashlib.sha256(f"{name}\n{reason}".encode()).hexdigest()[:12]
        group = groups.setdefault(
            key,
            {"reason": reason, "home": name, "rows": [], "numbers": [], "who": "crew", "lift": ""},
        )
        group["rows"].append(slug)
        group["numbers"].append(number)
        left = _tells_left(told, slug, number, reason)
        if left is None:
            group["who"] = "user"
            group["lift"] = judgement.ACCEPT if judgement.accepted(reason) else ""
        elif left:
            owed.add(key)
    busy = [one["slug"] for one in out if one.get("live") in AT_WORK and one.get("slug")]
    kept: dict[str, Any] = {}
    for key, group in groups.items():
        crews = bound(group["reason"]).owner == CREW
        if crews and any(_on(slug, group["reason"], group["rows"]) for slug in busy):
            continue
        hold = {"since": run.now.isoformat(), "woke": False} | was.get(key, {}) | group
        minutes = int((run.now - datetime.fromisoformat(hold["since"])).total_seconds() // 60)
        hold["minutes"] = minutes
        kept[key] = hold
        if hold["woke"]:
            continue
        if hold["lift"]:
            hold["woke"] = True
            pairs = zip(hold["rows"], hold["numbers"], strict=True)
            rows = ", ".join(f"{slug} (#{number})" for slug, number in pairs)
            said = (
                f"{HELD} {run.project.name}: {rows} held by {hold['reason']}, which no crew "
                f"clears: it is the user's, and {hold['lift']} lifts it"
            )
            run.find("", HELD, said, key=f"{key} {hold['since']}")
            run.say(said)
            continue
        if minutes <= HOLD_MINUTES:
            continue
        if hold["who"] == "crew" and key in owed:
            continue
        pairs = zip(hold["rows"], hold["numbers"], strict=True)
        rows = ", ".join(f"{slug} (#{number})" for slug, number in pairs)
        text = HELD_HOME.format(rows=rows, minutes=minutes, reason=hold["reason"])
        at = thread_of(run.home / hold["home"])
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
