"""Keep `review-launches.jsonl` in the project's state: one line for each reviewer thread, with
the head it was launched at, so that whether a review repeats one of the same head is read from
what jbus asked, not guessed from CI.

A line is a `Launch`: the row's slug, the reviewer's thread, the full head it was asked to read,
its kind (`first`, a reviewer of the review before the pull request, `jbus.prereview`, or
`scoped`, a reviewer of a change since a review, `jbus.rebase.scope` or one a crew launched), its
seat `n` (the `#<n>` of a `Reviewer:` line, 1 for a scoped one) and when it launched. `record` is
the one writer, and writes no second line for a thread the file holds.

`prereview.launch` and `rebase.scope` record each reviewer they launch, as they launch it. A crew
that launches a scoped reviewer itself writes `Scoped reviewer: <thread>, of <head>` under its
Result, and `scoped` records each such line of an open pull request's brief that the file lacks,
at the time the pass first reads it. A `Reviewer:` line names no head, so a first reviewer jbus
did not launch has no line.

The telemetry store reads the file into `review_heads` (`jbus.telemetry.records.review_heads`),
whose head the view `review_launches` gives each reviewer thread.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from jbriefs import below
from jbus import history, verbs
from jbus.passes import Pass
from jbus.watch import World, task_brief

LAUNCHES = "review-launches.jsonl"
SCOPED = "Scoped reviewer"
_HEAD = re.compile(r"[0-9a-f]{7,40}")


@dataclass(frozen=True)
class Launch:
    slug: str
    thread: str
    head: str
    kind: Literal["first", "scoped"]
    n: int
    at: datetime


def record(run: Pass, launch: Launch) -> None:
    """Add the launch's line to the project's `review-launches.jsonl`, unless the file holds its
    thread."""
    line: dict[str, Any] = asdict(launch) | {"at": launch.at.isoformat()}
    history.add(run.state / LAUNCHES, [line], lambda one: one.get("thread"))


def said(line: str) -> tuple[str, str] | None:
    """The thread and the head of what a `Scoped reviewer:` line says, `<thread>, of <head>`, or
    None where it names no reviewer or no head."""
    words = line.split()
    if len(words) != 3 or words[1] != "of" or not _HEAD.fullmatch(words[2]):
        return None
    thread = words[0].rstrip(",")
    return (thread, words[2]) if below.launched(thread) else None


def scoped(run: Pass, world: World) -> None:
    """Record each `Scoped reviewer:` line of an open pull request's brief: see the module."""
    for slug in sorted(world.open):
        for line in below.reviewers(task_brief(run, slug), SCOPED):
            found = said(line)
            if found:
                record(run, Launch(slug, found[0], found[1], "scoped", 1, run.now))


def _step(half: Any) -> None:
    if half.seen.world is not None:
        scoped(half.run, half.seen.world)


STEPS = (verbs.Step("tellers", 53, "reviewlaunch.scoped", _step, ("world",)),)
