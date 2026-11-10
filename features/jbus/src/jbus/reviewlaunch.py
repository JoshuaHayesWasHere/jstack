"""Keep `review-launches.jsonl` in the project's state: one line for each reviewer thread, with
the head it was launched at, so that whether a review repeats one of the same head is read from
what jbus asked, not guessed from CI.

A line is a `Launch`: the row's slug, the reviewer's thread, the full head it was asked to read,
its kind (`first`, a reviewer of the review before the pull request, `jbus.prereview`, or
`scoped`, a reviewer of a change since a review, `jbus.rebase.scope` or one a crew launched), its
seat `n` (the `#<n>` of a `Reviewer:` line, 1 for a scoped one, 0 for a claim) and when it
launched. `record` is the one writer, and writes no second line for a thread the file holds.

`prereview.launch` and `rebase.scope` ask `has` before they launch, `claim` the head before
`t3_thread_launch`, `release` it where T3 Code refuses the launch, and `record` each reviewer they
launch, as they launch it. A claim is a line with no thread, written before the launch since a
launch has no retry key: a pass that crashes after it launches no reviewer of the head twice. The
claim stays once the launch's own line follows it. A crew that launches a scoped reviewer itself
writes `Scoped reviewer: <thread>, of <head>` under its Result, and `scoped` records each such
line of an open pull request's brief that the file lacks, at the time the pass first reads it. A
`Reviewer:` line names no head, so a first reviewer jbus did not launch has no line.

`has` is the one answer to whether a head has a review asked for: a line of the file at the head,
claim or launch, or a key `sent.json` holds of it. Before the claim, a launch marked
`reviewers|<slug>|<head 12>` or `rereview|<slug>|<head 12>` there, and `expedite` still sends its
`rereview` row's message to the crew under the second, so a head whose crew was asked to launch
the scoped reviewer itself gets none from `rebase.scope`. Keep reading both.

The telemetry store reads the file into `review_heads` (`jbus.telemetry.records.review_heads`),
whose head the view `review_launches` gives each reviewer thread.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from jbriefs import below
from jbus import history, verbs
from jbus.passes import Pass
from jbus.watch import World, task_brief
from jmerge import ready

LAUNCHES = "review-launches.jsonl"
SCOPED = "Scoped reviewer"
_HEAD = re.compile(r"[0-9a-f]{7,40}")
_MARKED = ("reviewers", "rereview")
Kind = Literal["first", "scoped"]


@dataclass(frozen=True)
class Launch:
    slug: str
    thread: str
    head: str
    kind: Kind
    n: int
    at: datetime


def record(run: Pass, launch: Launch) -> None:
    """Add the launch's line to the project's `review-launches.jsonl`, unless the file holds its
    thread."""
    line: dict[str, Any] = asdict(launch) | {"at": launch.at.isoformat()}
    history.add(run.state / LAUNCHES, [line], _key)


def claim(run: Pass, slug: str, head: str, kind: Kind) -> None:
    """Write that a reviewer of `head` is about to launch, before `t3_thread_launch`: a line
    that names no thread."""
    record(run, Launch(slug, "", head, kind, 0, run.now))


def release(run: Pass, slug: str, head: str, kind: Kind) -> None:
    """Take back the claim of a launch T3 Code refused, so that the next pass asks again."""
    path = run.state / LAUNCHES
    try:
        lines = path.read_text(errors="replace").splitlines(keepends=True)
    except FileNotFoundError:
        return
    gone = ("claim", slug, head, kind)
    kept = [line for line in lines if _key(_parsed(line)) != gone]
    if len(kept) == len(lines):
        return
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text("".join(kept))
    os.replace(temporary, path)


def has(run: Pass, slug: str, head: str) -> bool:
    """Whether `head` has a review asked for: see the module."""
    short = head[:12]
    held = history.held(run.state / LAUNCHES, lambda one: (one.get("slug"), _short(one)))
    if (slug, short) in held:
        return True
    sent = run.box.sent()
    return any(f"{kind}|{slug}|{short}" in sent for kind in _MARKED)


def judged(run: Pass, slug: str, head: str) -> bool:
    """Whether the last review the brief has written judged `head`: a reviewer asked for there
    would read what that review read, so `expedite` asks a crew for none."""
    return ready.said_of(task_brief(run, slug)).reviewed == head


def _key(one: dict[str, Any]) -> Any:
    """A launch is its thread, and a claim its slug, head and kind."""
    return one.get("thread") or ("claim", one.get("slug"), one.get("head"), one.get("kind"))


def _short(one: dict[str, Any]) -> str:
    return str(one.get("head") or "")[:12]


def _parsed(line: str) -> dict[str, Any]:
    try:
        one = json.loads(line)
    except ValueError:
        return {}
    return one if isinstance(one, dict) else {}


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
