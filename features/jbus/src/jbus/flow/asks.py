"""`jbus flow asks`: how many times the owner asked a thread for a status, per job and per day.

It reads the owner's messages from T3 Code's store as `jbus flow nudges` does (`nudges.read`,
`nudges.words`), from every thread by default, since the owner asks crews and scratch threads
too. A message is an ask when it matches the words of at least one job of `JOBS`, the jobs of
the scout `jview-asks`' Report: J1 to J6 of `jview-ux-a`, the three new jobs J7 to J9, and VW,
an ask about the view itself. One message can ask for more than one job, as "$ketchup, are we
flowing again?" asks J2 and J1, and counts once as an ask and once under each job it asks.

Each message the owner typed counts, the same words typed to three homes included, since each
home answers its own. A word jbus carried to a home (`jbus.word.MESSAGE`) counts unless the
owner typed the same words in another thread within 10 minutes: then it is that message again.

The scout coded the asks by hand. `JOBS` is that coding made deterministic, so that a week's
count compares with the last: the count that should fall as jview answers the jobs itself.
`asks` and `count` are pure over `nudges.Said` records, so a test drives them with no store.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

from jbus.flow import nudges

DEFINITION = (
    "Definition: an ask is a message from Josh, in any thread, that asks for a status, a visual "
    "update or a look at the queue, the plan or the machine, by the jobs of the jview-asks "
    "Report: J1 is work moving or why it stalled, J2 where we are and the queue, J3 what needs "
    "him, J4 the machine, CI and runners, J5 whether a thing landed, J6 why he is asked, J7 the "
    "plan and how close a milestone is, J8 every home at once, J9 how much got done, VW the "
    "view itself. One message can ask for more than one job. A slash command, an approval with "
    "no question and new work are not asks."
)
TITLE = "%"


@dataclass(frozen=True)
class Job:
    """One job the owner asks a thread to do for him, and the words that ask it."""

    code: str
    name: str
    words: re.Pattern[str]


def _words(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(alternatives), re.I)


JOBS = (
    Job(
        "J1",
        "moving, or why it stalled",
        _words(
            r"\bstall",
            r"\bstuck\b",
            r"\bmoving\b",
            r"\bflowing\b",
            r"why .{0,40}\bwait",
            r"what are we waiting",
            r"push you",
            r"\bp(ro|or)gress\b",
            r"\blull\b",
            r"slowing us",
            r"moving slow",
            r"what (else )?is stopping",
            r"not (be )?merging",
            r"in parallel",
            r"racing",
            r"was .{0,20}\bheld\b",
            r"go(ne)? red",
        ),
    ),
    Job(
        "J2",
        "where we are, and the queue",
        _words(
            r"\$ketchup",
            r"where we are",
            r"state of the (the )?queue",
            r"(^|[.?!] )status\b",
            r"overview",
            r"work in progress",
            r"in progress across",
            r"what is done",
            r"what has been done",
            r"(^|[.?!] )and now\b",
            r"visual update",
            r"current status",
        ),
    ),
    Job(
        "J3",
        "what needs him",
        _words(r"needs? me\b", r"waits? on me", r"i need to run"),
    ),
    Job(
        "J4",
        "the machine, CI and runners",
        _words(
            r"\bmachine\b",
            r"\bload\b",
            r"what is ru?nn?ing",
            r"stress testing",
            r"\brunners?\b",
            r"\bcompute\b",
            r"the run \d+ minutes",
            r"app running",
        ),
    ),
    Job(
        "J5",
        "whether a thing landed",
        _words(
            r"\blanded\b",
            r"\bdeploy(ed)?\b",
            r"is (this|work) (done|complete)",
            r"all done",
            r"reinstalled",
            r"status of",
            r"did you merge",
            r"ready to close",
            r"discovered",
            r"benchmark find",
            r"other work is done",
        ),
    ),
    Job("J6", "why he is asked", _words(r"why is this being asked", r"what are these\b")),
    Job(
        "J7",
        "the plan, and how close a milestone is",
        _words(
            r"\bplan\b",
            r"how close",
            r"left in this queue",
            r"what remains",
            r"blocking us",
            r"work chains",
            r"action items",
            r"\bprogress compare",
        ),
    ),
    Job(
        "J8",
        "every home at once",
        _words(r"child homes", r"(across|through) the jstack homes", r"each home", r"every home"),
    ),
    Job(
        "J9",
        "how much got done",
        _words(r"how much work", r"this week stat", r"completed tonight"),
    ),
    Job("VW", "the view itself", _words(r"\bjview\b", r"jbus view", r"monitor the status")),
)
ASKING = re.compile(
    r"\?|\$ketchup|^\W*(\w+, *)?(what|why|how|where|is|are|did|does|has|have|can|will)\b"
    r"|\b(show|give|provide|generate) me\b|\bvisual\b|\btake a .{0,20}\blook\b",
    re.I,
)
"""A sentence asks when it is a question, a `$ketchup`, or asks to be shown a thing."""
SENTENCE = re.compile(r"(?<=[.?!])\s+|\n+")


@dataclass(frozen=True)
class Ask:
    """One of the owner's messages that asks, its first line, and each job it asks, in `JOBS`'
    order."""

    message: nudges.Message
    first: str
    jobs: tuple[str, ...]


def jobs(text: str) -> tuple[str, ...]:
    """Return the code of each job `text` asks, in `JOBS`' order: the jobs whose words are in
    one of its sentences that asks (`ASKING`), or in the sentence before it, as "we seem
    stalled. why?" asks why it stalled. A text that asks for no job gives none."""
    sentences = SENTENCE.split(text)
    asking = [
        " ".join(sentences[max(n - 1, 0) : n + 1])
        for n, one in enumerate(sentences)
        if ASKING.search(one)
    ]
    return tuple(job.code for job in JOBS if any(job.words.search(one) for one in asking))


def messages(found: list[nudges.Message], since: datetime, until: datetime) -> list[nudges.Message]:
    """Return the owner's messages in `[since, until)`, oldest first, each with his words for
    its text, links left out: each one he typed, and a word jbus carried unless he typed its
    words in another thread within 10 minutes. A slash command and an empty text are none."""
    kept: list[nudges.Message] = []
    for one in sorted(found, key=lambda each: each.at):
        said = nudges.words(one)
        if said is None or not since <= one.at < until:
            continue
        said = nudges.LINK.sub("", said).strip()
        if said and not said.startswith("/"):
            kept.append(replace(one, text=said))

    def head(one: nudges.Message) -> str:
        return nudges.flat(one.text)[: nudges.SAME].lower()

    return [
        one
        for one in kept
        if one.by == "user"
        or not any(
            other.by == "user"
            and other.thread != one.thread
            and head(other) == head(one)
            and abs((one.at - other.at).total_seconds()) < nudges.CARRY_SECONDS
            for other in kept
        )
    ]


def asks(said: list[nudges.Message]) -> list[Ask]:
    """Return each of the owner's messages `said` that asks for a job, with its jobs."""
    found = [Ask(one, nudges.flat(one.text.splitlines()[0]), jobs(one.text)) for one in said]
    return [one for one in found if one.jobs]


def count(found: list[Ask], day: Callable[[datetime], date]) -> dict[str, Any]:
    """Return the asks' total, and the count per job and per day, each day as `day` gives it:
    `jobs` per job over the window, and `days`, for each day with an ask, its asks and the
    count per job. An ask of two jobs counts once in `asks` and once under each job."""
    days: dict[str, list[Ask]] = {}
    for one in found:
        days.setdefault(day(one.message.at).isoformat(), []).append(one)

    def per_job(asked: list[Ask]) -> dict[str, int]:
        return {job.code: sum(job.code in one.jobs for one in asked) for job in JOBS}

    return {
        "asks": len(found),
        "jobs": per_job(found),
        "days": {
            when: {"asks": len(asked), "jobs": per_job(asked)}
            for when, asked in sorted(days.items())
        },
    }


def text(found: list[Ask], said: list[nudges.Message], counted: dict[str, Any]) -> str:
    """Return each ask as a line, its time, jobs, home and first line, then one line per day of
    its count per job and its asks, a line of the window's, and the count of messages."""
    out = [
        f"{one.message.at.astimezone(UTC):%Y-%m-%dT%H:%MZ}\t{','.join(one.jobs)}\t"
        f"{one.message.home}\t{one.first[:100]}"
        for one in found
    ]
    codes = [job.code for job in JOBS]
    out += ["", "\t".join(["day", *codes, "asks"])]
    for when, that in counted["days"].items():
        out.append(
            "\t".join([when, *(str(that["jobs"][code]) for code in codes), str(that["asks"])])
        )
    out.append(
        "\t".join(["all", *(str(counted["jobs"][code]) for code in codes), str(counted["asks"])])
    )
    return "\n".join([*out, f"messages {len(said)}, asks {counted['asks']}"])
