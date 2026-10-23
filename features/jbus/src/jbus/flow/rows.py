"""Each row's time in a window, from the queue's table in `events.jsonl`, as working or waiting.

A pass writes a `queue` event when the table changed. Its text holds, under the lines that say
what changed, the table of every row that changed, each with all of its columns. So the
events give each row's status, checks, approval and `why` over time, and a row keeps the state
of its last line until the next line about it.

`walk` reads those lines. A row's clock starts at the first line that shows it approved. It
stops when the row is merged or done, or when an `item.dropped` event says the row was
removed. A row first seen merged or done has no clock: its time is before the records. In
between, each stretch between two lines is a `Span` in the state of the first. A crew at work
(`launched`, `running`) is working, and everything else is waiting, with the reason
`classify` gives it. `classify` reads only the status, the `why` and the checks, the same
words `jbus queue show` prints, and a state it cannot place is `unexplained`.

The table's `why` of a pull request can stay as it was while `jmerge` says something new of
it: a pass writes a row's line only when a column of the row changed. So a `jmerge` event that
waits on or holds a row's pull request is the row's `why` from then on, until the next line.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from jmerge import lines

WORKING = frozenset({"launched", "running"})
ENDED = frozenset({"merged", "done"})
WORK = "work"
UNEXPLAINED = "unexplained"
CHECK_WAIT = re.compile(
    r"^pr / wait: (check has not passed|borders has not passed|a fresh check is queued"
    r"|GitHub has not decided)"
)
RULES = tuple(
    (stage, name, re.compile(pattern))
    for stage, name, pattern in (
        ("review", "first review not written", r"^pr / wait: it has no review yet"),
        (
            "review",
            "second or scoped review not written",
            r"^pr / wait: (its second review is not written|its fix is not reviewed"
            r"|its review has no verdict|the scoped review has not ruled"
            r"|the rebase changed the content after its review)",
        ),
        ("findings", "findings not handled", r"^pr / wait: its findings are not handled"),
        (
            "check",
            "fresh check over today's main failed",
            r"^pr / wait: .* fails on \S+ over today",
        ),
        ("check", "check running or queued", r"^pr / wait: main changed .* needs a fresh check"),
        ("josh", "held for his word", r"^pr / wait: its crew held a third rebase"),
        ("tool", "the merge call failed", r"^pr / wait: the merge failed"),
        ("queue", "merges after another row", r"^pr / wait: merges after "),
        ("main", "main or its train is red", r"^pr / wait: \S+ is red at"),
        ("conflict", "conflict or rebase", r"^pr / wait: (it conflicts|the rebase dropped)"),
        ("tool", "no Result names the pull request", r"^pr / wait: no brief has a Result"),
        ("tool", "base is not main", r"^pr / wait: its base is \S+, not main"),
        ("crew", "draft", r"^pr / wait: draft"),
        ("josh", "held for his word", r"^pr / (hold:|wait: its queue row is held)"),
        ("josh", "approval voided, brief changed", r"^gate / brief changed after approval"),
        ("josh", "a gate", r"^gate / "),
        ("josh", "not approved", r"^queued / not approved"),
        ("queue", "depends on another row", r"^queued / depends on"),
        ("machine", "no slot or room", r"^queued / no (slot|room)"),
        ("queue", "waiting to launch", r"^queued / $"),
        ("stopped", "thread ended with no Result", r"^stale / "),
        ("stopped", "ended with something left", r"^left / "),
        ("stopped", "launch failed", r"^failed / "),
    )
)
DROPPED = re.compile(r"\brow (\S+) was removed\b")


@dataclass(frozen=True)
class State:
    """A row's state on one line of the table."""

    status: str
    why: str
    checks: str
    approved: bool


@dataclass(frozen=True)
class Span:
    """A stretch of one row's time in one state, `stage` and `name` as `classify` gives them."""

    start: datetime
    end: datetime
    stage: str
    name: str

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass
class Row:
    """A row's clock: from its first approval to its end, in spans. `end` is `merged`, `done`
    or `removed`, and empty for a row still open at the end of the window."""

    project: str
    slug: str
    approved: datetime | None = None
    ended: datetime | None = None
    end: str = ""
    spans: list[Span] = field(default_factory=list)

    def hours(self, working: bool) -> float:
        return sum(one.hours for one in self.spans if (one.stage == WORK) == working)


def classify(state: State) -> tuple[str, str]:
    """Return the stage and the reason of a state. A crew at work is the stage `work`."""
    if state.status in WORKING:
        return WORK, "crew at work"
    said = f"{state.status} / {state.why}"
    if CHECK_WAIT.match(said):
        if state.checks == "failed":
            return "check", "check failed, nobody acting"
        return "check", "check running or queued"
    for stage, name, pattern in RULES:
        if pattern.match(said):
            return stage, name
    if not state.approved and state.status == "queued":
        return "josh", "not approved"
    return UNEXPLAINED, f"{state.status}: {state.why.split(':')[0] or 'no why'}"


def read(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the events of a log in order, past any line that does not parse."""
    try:
        lines = path.open(errors="replace")
    except OSError:
        return
    with lines:
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and isinstance(event.get("at"), str):
                yield event


def table(text: str) -> Iterator[tuple[str, State, str]]:
    """Yield each row of the tables in a `queue` event's text: its slug, its state, and the
    number of its pull request, empty where it has none."""
    header: list[str] = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if cells and cells[0] == "slug":
            header = cells
            continue
        if not header or len(cells) != len(header):
            continue
        got = dict(zip(header, cells, strict=True))
        state = State(
            got.get("status", ""), got.get("why", ""), got.get("checks", ""), bool(got["approved"])
        )
        yield got["slug"], state, got.get("pr", "").lstrip("#")


def at(event: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(event["at"])
    except ValueError:
        return None


def walk(project: str, events: Iterable[dict[str, Any]], until: datetime) -> list[Row]:
    """Return every row that was approved, with its spans up to its end or `until`."""
    rows: dict[str, Row] = {}
    last: dict[str, tuple[datetime, State]] = {}
    pulls: dict[str, str] = {}

    def close(slug: str, when: datetime) -> None:
        if slug in last and rows[slug].approved is not None:
            since, state = last[slug]
            if when > since:
                stage, name = classify(state)
                rows[slug].spans.append(Span(since, when, stage, name))

    for event in events:
        when = at(event)
        if when is None or when > until:
            continue
        if event.get("event") == "item.dropped":
            found = DROPPED.search(str(event.get("line", "")))
            if found and found[1] in last and not rows[found[1]].end:
                close(found[1], when)
                rows[found[1]].ended, rows[found[1]].end = when, "removed"
                del last[found[1]]
            continue
        if event.get("event") == "jmerge":
            said = lines.one(str(event.get("line", "")))
            waits = said is not None and said.word in ("wait", "hold") and bool(said.reason)
            slug = pulls.get(str(said.number), "") if said and waits else ""
            if said and slug in last and last[slug][1].status == "pr":
                close(slug, when)
                last[slug] = when, replace(last[slug][1], why=f"{said.word}: {said.reason}")
            continue
        if event.get("event") != "queue":
            continue
        for slug, state, pull in table(str(event.get("text") or "")):
            if pull:
                pulls[pull] = slug
            row = rows.setdefault(slug, Row(project, slug))
            if row.end:
                continue
            close(slug, when)
            if state.status in ENDED and slug not in last:
                continue
            if state.approved and row.approved is None:
                row.approved = when
            if state.status in ENDED:
                if row.approved is not None:
                    row.ended, row.end = when, state.status
                last.pop(slug, None)
                continue
            last[slug] = when, state
    for slug in list(last):
        close(slug, until)
    return [row for row in rows.values() if row.approved is not None]


def clip(rows: Iterable[Row], since: datetime, until: datetime) -> list[tuple[Row, Span]]:
    """Return every span of the rows cut to the window, each beside its row."""
    cut = []
    for row in rows:
        for one in row.spans:
            start, end = max(one.start, since), min(one.end, until)
            if end > start:
                cut.append((row, Span(start, end, one.stage, one.name)))
    return cut
