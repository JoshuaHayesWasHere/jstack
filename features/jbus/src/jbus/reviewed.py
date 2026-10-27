"""Tell a crew of its review when the crew owes a line for it. A reviewer used to send its findings
itself, and decided in the shell of its skill whether the crew had work. It no longer sends
anything: its one output is the `## Review` section in the brief.

`tell` reads each open pull request's brief on each pass. The review it reads is the newest head
that a section ran at, with every section of that head, one for each reviewer. It asks jmerge's
judge, `ready.short_of`, what the pull request is short of at its head. Only where that reason is a
line the crew owes (`OWED`: findings to answer, or a `Fixed:` line) does it send the crew one
message, through `jbus.outbox`, with needs `act`, under the key `review|<slug>|<head 12>` of the
head the sections reviewed. The message names the sections by their `By:` lines and the findings
of that head by their ids. A clean verdict, the second review of a `Review: twice` brief that its
reviewer filed as `cleanup-<slug>`, a `Review: after` brief and a review whose other seats have not
written yet all owe no line, so nothing is sent and `outbox.jsonl` has no line for them.

A brief with no `Thread:` line names no crew, so its home is sent the notice in its place. With no
home either, the findings are a gate, once for the head. A section whose `Sent to:` line starts
with a thread id was sent by a reviewer that still runs the skill text from before this rule, and
gets no second copy.

The message waits for the next pass, the same wait every other message of jbus has, and the outbox
holds it while the crew is at work (`outbox.RULES`). A held notice is judged again on each pass, so
one whose line the crew wrote meanwhile is never sent. Once it goes, it also counts as `expedite`'s
message for the same reason and head, so the crew is not told the same thing again three passes
later. A reason that stays after the notice, at the same head, is `expedite`'s from there on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from jbriefs import findings, parse
from jbus import END_TURN, mirror, outbox, rebase, verbs
from jbus.expedite import ANSWERED, TABLE, Short
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import World, home_thread, task_brief
from jmerge import ready

if TYPE_CHECKING:
    from jbus.cli import Half

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


def _judged(brief: str, head: str) -> str:
    """Return what jmerge's judge says the pull request is short of, as far as its review goes. The
    judge asks for each skill's artifact before it reads the review, so a Result that still lacks
    one would hide the findings it owes an answer: the review is judged as if the brief named no
    skill."""
    said = ready.short_of(brief, head)
    if not re.fullmatch(ready.SKILLS_UNRUN.pattern, said):
        return said
    return ready.short_of(_SKILLS.sub("Skills: none", brief, count=1), head)


def due(brief: str, head: str) -> Notice | None:
    """Return the notice that the newest review of the brief owes its crew while the pull request's
    head is `head`, or None where the crew owes no line for it."""
    triage = findings.triage(brief)
    ran = [one for one in triage.sections if one.ran and one.head]
    if not ran or mirror.delivered(brief):
        return None
    reviewed = ran[-1].head
    reason = _judged(brief, head)
    row = next((one for one in TABLE if one.reason.fullmatch(reason)), None)
    if row is None or row.kind not in OWED:
        return None
    at = [
        one for one in triage.findings if one.sent and any(r.head == reviewed for r in one.raised)
    ]
    found = tuple(findings.listed(replace(triage, findings=at)))
    by = tuple(dict.fromkeys(one.by for one in ran if one.head == reviewed and one.by))
    return Notice(reviewed, by, row, reason, found)


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
        notice = due(brief, head) if brief and head else None
        key = notice.key(slug) if notice else ""
        if not notice or key in sent:
            continue
        thread = parse.thread_of(brief) or home_thread(run, brief)
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
    tell(half.run, half.client, half.seen.world)


STEPS = (verbs.Step("tellers", 52, "reviewed.tell", _step, ("client", "world")),)
