"""Tell a crew of its review when the crew owes a line for it. A reviewer used to send its findings
itself, and decided in the shell of its skill whether the crew had work. It no longer sends
anything: its one output is the `## Review` section in the brief.

`tell` reads each open pull request's brief on each pass. The review it reads is the newest head
that a section ran at, with every section of that head, one for each reviewer. It asks jmerge's
judge, `ready.short_of`, what the pull request is short of at its head, with the `Waived:` lines
`jmerge` counts (`outbox.heard`). Only where that reason is a
line the crew owes (`OWED`: findings to answer, or a `Fixed:` line) does it send the crew one
message, through `jbus.outbox`, with needs `act`, under the key `review|<slug>|<head 12>` of the
head the sections reviewed. The message names the sections by their `By:` lines and the findings
of that head by their ids. A clean verdict and a review whose other seats have not written yet owe
no line, so nothing is sent and `outbox.jsonl` has no line for them.

A brief with no `Thread:` line names no crew, so its home is sent the notice in its place. With no
home either, the findings are a gate, once for the head. A section whose `Sent to:` line starts
with a thread id was sent by a reviewer that still runs the skill text from before this rule, and
gets no second copy.

The message waits for the next pass, the same wait every other message of jbus has, and the outbox
holds it while the crew is at work (`outbox.RULES`). A held notice is judged again on each pass, so
one whose line the crew wrote meanwhile is never sent. Once it goes, it also counts as `expedite`'s
message for the same reason and head, so the crew is not told the same thing again three passes
later. A reason that stays after the notice, at the same head, is `expedite`'s from there on.

`rounds` keeps `review-rounds.jsonl` in the project's state, one line for each review round of a
row's pull request, which the telemetry store copies (`review_rounds`). A round is the sections
in a row that ran (`Verdict: clean` or `findings`) at one head, a scoped pass a round of its own.
Its line names the row, the pull request, the round's number from 1, its head, whether it is
scoped and how many sections it has, the round's `Meets the brief` verdict (`yes` where each
section says yes, `no` where one says no, else `unread`, as `meets.parse` reads the line) with
the least `met` of `done_when`, and the count of its findings by severity, and of those
dismissed. It is written on the pass that sees the round settled: a later round has begun, or no
reviewer the crew launched still owes its section (`reviewers.running`). A round is written once,
by row and number, so a pass that reads it again writes nothing, and a round written to the
brief after its line keeps the line it had. A row whose pull request the pass's world shows
merged within `MERGED_WITHIN` has every round settled, since no section is still to come, so the
last round of a pull request that merged before a pass saw it settled gets its line on the first
pass that sees the merge. The window keeps a pass from reading the brief of every merge it keeps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING

from jbriefs import findings, meets, reviewers
from jbriefs.home import home_of, thread_of
from jbus import END_TURN, history, mirror, outbox, rebase, verbs
from jbus.expedite import ANSWERED, TABLE, Short
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, task_brief, when
from jmerge import ready

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"reviewed": "quiet"}
TEMPLATE = "reviewed"
OWED = frozenset({*ANSWERED, "overruled"})
"""The kinds of `expedite.TABLE` whose reason is a line the crew owes for a review it was sent:
an answer for each finding, by id, and the `Fixed:` line, or a fix for a decline the scoped pass
did not uphold."""
NO_THREAD = "review findings with no thread to send them to"
REFUSED = "T3 Code refused the review's findings"
MESSAGE = (
    "jbus: {slug}'s pull request #{number} at {head} has its review, in the brief's `## Review` "
    "{sections}, and jmerge says it waits on you: {reason}. {sentence}\n\n"
    "The findings of that review, by id (`jbriefs --findings` on the brief lists every one):\n"
    "{found}\n\n" + END_TURN
)
_SKILLS = re.compile(r"^Skills:.*$", re.M)


@dataclass(frozen=True)
class Notice:
    """What one review asks of its crew: the head its sections reviewed, their `By:` lines, the
    row of `expedite.TABLE` that jmerge's reason matches, the reason itself, and the findings of
    that head, as `jbriefs --findings` lists them."""

    head: str
    by: tuple[str, ...]
    row: Short
    reason: str
    found: tuple[str, ...]

    def key(self, slug: str) -> str:
        return f"review|{slug}|{self.head[:12]}"


def _judged(brief: str, head: str, heard: frozenset[meets.Waiver]) -> str:
    """Return what jmerge's judge says the pull request is short of, as far as its review goes,
    with the `Waived:` lines in `heard`. The judge asks for each skill's artifact before it
    reads the review, so a Result that still lacks one would hide the findings it owes an answer:
    the review is judged as if the brief named no skill."""
    said = ready.short_of(brief, head, heard)
    if ready.code_of(said) != ready.SKILLS_UNRUN.code:
        return said
    return ready.short_of(_SKILLS.sub("Skills: none", brief, count=1), head, heard)


def due(brief: str, head: str, heard: frozenset[meets.Waiver] = frozenset()) -> Notice | None:
    """Return the notice that the newest review of the brief owes its crew while the pull request's
    head is `head`, or None where the crew owes no line for it. `heard` holds the `Waived:`
    lines whose words jbus checked (`outbox.heard`), as `jmerge` counts them."""
    triage = findings.triage(brief)
    ran = [one for one in triage.sections if one.ran and one.head]
    if not ran or mirror.delivered(brief):
        return None
    reviewed = ran[-1].head
    reason = _judged(brief, head, heard)
    row = next((one for one in TABLE if one.reason.code == ready.code_of(reason)), None)
    if row is None or row.kind not in OWED:
        return None
    at = [
        one for one in triage.findings if one.sent and any(r.head == reviewed for r in one.raised)
    ]
    found = tuple(findings.listed(replace(triage, findings=at)))
    by = tuple(dict.fromkeys(one.by for one in ran if one.head == reviewed and one.by))
    return Notice(reviewed, by, row, reason, found)


ROUNDS = "review-rounds.jsonl"
SEVERITIES = {"error": "errors", "warning": "warnings", "info": "infos"}
MERGED_WITHIN = timedelta(days=7)
"""How long after its merge a row's rounds are still read: a pass that sees the merge writes the
last round's line, and a week covers a jbus that was down a while."""


def _verdict(brief: str, sections: list[findings.Section]) -> tuple[str, int | None, int | None]:
    """The round's `Meets the brief` word, the least `met` and the `of` its sections give."""
    read = [meets.parse(meets.lines_of(brief, one)) for one in sections]
    typed = [one for one in read if one is not None]
    word = (
        meets.NO
        if any(one.word == meets.NO for one in typed)
        else meets.YES
        if typed and len(typed) == len(read)
        else meets.UNREAD
    )
    met = min((one.met for one in typed), default=None)
    return word, met, typed[0].of if typed else None


def round_lines(brief: str, slug: str, number: int, at: str, merged: bool = False) -> list[dict]:
    """The line of each settled review round of the brief, as `rounds` writes it. Every round of
    a `merged` pull request is settled."""
    ran = [one for one in findings.triage(brief).sections if one.ran and one.head]
    grouped: list[list[findings.Section]] = []
    for one in ran:
        last = grouped[-1][-1] if grouped else None
        if last is not None and (last.head, last.scoped) == (one.head, one.scoped):
            grouped[-1].append(one)
        else:
            grouped.append([one])
    if grouped and not merged and reviewers.running(brief):
        grouped.pop()
    lines = []
    for place, sections in enumerate(grouped, start=1):
        word, met, of = _verdict(brief, sections)
        counts = dict.fromkeys((*SEVERITIES.values(), "others", "dismissed"), 0)
        for raised in (one for section in sections for one in section.raised):
            if raised.bucket == findings.DISMISSED:
                counts["dismissed"] += 1
            else:
                counts[SEVERITIES.get(raised.severity.lower(), "others")] += 1
        lines.append(
            {
                "at": at,
                "slug": slug,
                "pr": number,
                "round": place,
                "head": sections[0].head,
                "scoped": sections[0].scoped,
                "sections": len(sections),
                "meets": word,
                "met": met,
                "of": of,
                **counts,
            }
        )
    return lines


def _round_key(one: dict) -> tuple:
    return one.get("slug"), one.get("pr"), one.get("round")


def rounds(run: Pass, world: World) -> None:
    """Log each settled review round of each open or lately merged pull request's brief once: see
    the module."""
    at = run.now.isoformat()
    lately = {
        slug: pull
        for slug, pull in world.merged.items()
        if slug not in world.open
        and pull.get("mergedAt")
        and run.now - when(pull["mergedAt"]) <= MERGED_WITHIN
    }
    lines = []
    for pulls, merged in ((world.open, False), (lately, True)):
        for slug, pull in sorted(pulls.items()):
            brief = task_brief(run, slug)
            if brief and isinstance(pull.get("number"), int):
                lines += round_lines(brief, slug, pull["number"], at, merged)
    history.add(run.state / ROUNDS, lines, _round_key)


def _text(slug: str, number: int, notice: Notice) -> str:
    named = "; ".join(f"`By: {one}`" for one in notice.by) or "with no `By:` line"
    return MESSAGE.format(
        slug=slug,
        number=number,
        head=notice.head[:12],
        sections=named,
        reason=notice.reason,
        sentence=notice.row.sentence,
        found="\n".join(notice.found) or "none listed: answer what the reason names",
    )


def tell(run: Pass, client: Client, world: World) -> None:
    """Send each crew the notice its newest review owes it, once for the head reviewed."""
    sent = run.box.sent()
    for slug, pull in sorted(world.open.items()):
        brief = task_brief(run, slug)
        head = pull.get("headRefOid", "")
        notice = due(brief, head, outbox.heard(run, slug, brief)) if brief and head else None
        key = notice.key(slug) if notice else ""
        if not notice or key in sent:
            continue
        thread = thread_of(run.home, slug) or thread_of(home_of(run.home, brief))
        text = _text(slug, pull["number"], notice)
        if not thread:
            run.gate(slug, NO_THREAD, text, key=f"{NO_THREAD} {notice.head[:12]}")
            continue
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=slug,
                key=key,
                text=text,
                template=TEMPLATE,
                needs="act",
            )
        except T3Refused as error:
            run.gate(slug, REFUSED, f"{error}\n\n{text}", key=f"{REFUSED} {notice.head[:12]}")
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its review's findings could not be sent ({error})")
            continue
        if not went:
            continue
        run.box.mark(key)
        run.box.mark(rebase.mark(notice.row.kind, slug, head))
        line = f"reviewed {slug}: told {thread} of #{pull['number']} at {notice.head[:12]}"
        run.find(slug, "reviewed", line, text, key=notice.head[:12])
        run.say(line)


def _step(half: Half) -> None:
    client, world = half.client, half.seen.world
    if client is not None and world is not None:
        rounds(half.run, world)
        tell(half.run, client, world)


STEPS = (verbs.Step("tellers", 52, "reviewed.tell", _step, ("client", "world")),)
