"""How work flowed in a window, measured from the records of `jbus.flow.records`.

A row's time runs from its approval (the first time its `approved` column gives) to its merge
(GitHub's `mergedAt` for its pull request, else the event log's) or to the window's end, clipped
to the window. `row_spans` cuts that time into spans, each of one class (`CLASSES`) that says
what the row did or waited on: the class of its status, and for a row with a pull request, of
why it waits as the table or `jmerge` said it last. A span with no record before it is
`no record`. A span in which the event log says the row's account was capped, or its thread
waited for a test slot, takes that class instead of `crew at work`.

A class is `working` (the crew at work, or its checks running) or waiting. `unexplained` is
the waiting the records give no reason for: a row that waits with no why. `no record` is time
before the first record of a row, which no source covers: it is a reason of its own, counted and
printed apart from `unexplained`, never folded into another class. Each span keeps the record
that opened it (`Span.source`), so each hour traces to an event, a journal line or a run.

A row that waits behind its `depends` is `ordering`. `behind` follows each such span to the rows
it waited on, and on through theirs, to what the head of the chain was doing.
"""

from __future__ import annotations

import itertools
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jbus.flow.records import (
    Cap,
    Line,
    Mark,
    Project,
    Run,
    Said,
    Sighting,
    SlotWait,
    stamped,
    when,
)

WORKING = ("crew at work", "checks running")
NO_RECORD = "no record"
UNEXPLAINED = ("waits, no why recorded", "queued, no why recorded")
OWN_CHECK = "check"
"""The check jbus's `checks` column follows. Another check a pull request needs (`borders`) is
not in that column, so a row whose checks passed and that waits on another is waiting on a
check nothing reports, not working."""
REASONS = (
    (r"main is red|^\S+ is red at|is red at \w+: its latest", "main red"),
    (r"fails on \w+ over today's main|over today's main", "fails over today's main"),
    (r"fresh check|main changed .* after its check", "fresh check queued"),
    (r"no review yet|review has no verdict|second review is not written", "review not written"),
    (r"scoped review", "scoped review not written"),
    (r"findings are not handled|no Finding line", "findings not fixed"),
    (r"rebase (changed|dropped)|third rebase", "rebase rework"),
    (r"conflicts with", "conflict"),
    (r"^hold: needs|needs \S+, ", "owner: hand-merge"),
    (r"brief changed after approval", "owner: approval voided"),
    (r"held: approve it again|not approved", "owner: approval"),
    (r"gate", "owner: gate"),
    (r"no brief has a Result", "no Result names the PR"),
    (r"draft", "draft"),
    (r"^ready: ", "ready, not launched"),
    (r"its base is \S+, not main", "base is not main"),
    (r"depends on|merges after|behind|its base is", "ordering"),
    (r"no room|no slot", "no room"),
    (r"the merge failed", "merge call failed"),
    (r"GitHub has not decided", "GitHub merge"),
    (r"(\S+) has not passed", "check not passed"),
)
"""The first pattern that matches why a row waits names its class."""
STATUS = {
    "launched": "crew at work",
    "running": "crew at work",
    "stale": "thread stopped (stale)",
    "left": "ended with work left",
    "failed": "launch failed",
    "waiting": "crew asks the owner",
    "gate": "owner: gate",
}
OVER = ("merged", "done", "removed")
GAP = timedelta(minutes=5)
PASS = timedelta(minutes=1)


@dataclass(frozen=True)
class Span:
    start: datetime
    end: datetime
    what: str
    source: str = ""

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class Row:
    """One row's time in the window: `start` and `end` clipped, `merged` when it merged in it."""

    project: str
    slug: str
    approved: datetime | None
    merged: datetime | None
    spans: tuple[Span, ...]
    depends: tuple[str, ...] = ()

    def hours(self, working: bool | None = None) -> float:
        return sum(
            one.hours for one in self.spans if working is None or (one.what in WORKING) == working
        )


def why_class(why: str, checks: str = "") -> str | None:
    """Return the class of a row's why, or None where no pattern matches."""
    for pattern, name in REASONS:
        if found := re.search(pattern, why):
            if name == "check not passed":
                return _not_passed(found[1], checks)
            return name
    return None


def _not_passed(check: str, checks: str) -> str:
    if checks == "failed":
        return "check failed"
    if checks == "passed" and check != OWN_CHECK:
        return "required check not reported"
    return "checks running"


def state_class(status: str, checks: str, why: str) -> str:
    """Return the class of a row in `status` with its checks and why."""
    if status == "pr":
        if not why and checks == "pending":
            return "checks running"
        if not why and checks == "failed":
            return "check failed"
        return why_class(why, checks) or ("waits, no why recorded" if not why else "other: " + why)
    if status == "queued":
        return why_class(why) or "queued, no why recorded"
    return STATUS.get(status) or why_class(why) or f"status {status}"


def row_spans(
    project: Project,
    slug: str,
    since: datetime,
    until: datetime,
    merges: dict[str, datetime],
) -> Row | None:
    """Return the row's time in the window cut into spans, or None for a row that was over
    before the window, was never approved, or was dropped with no merge."""
    seen = sorted(project.sightings.get(slug, []), key=lambda one: one.at)
    if not seen:
        return None
    stamps = [t for one in seen if (t := stamped(one.approved))]
    stamps += [project.approvals[slug]] if slug in project.approvals else []
    approved = min(stamps, default=None)
    first_status = seen[0].status
    went = next((one.at for one in seen if one.status not in ("queued", "gate")), None)
    if approved is None and (went is None or first_status in OVER):
        return None
    numbers = {one.pr for one in seen if one.pr}
    merged = _merged(project, slug, numbers, seen, merges)
    if merged is None and first_status in OVER:
        return None
    start = max(approved or went or seen[0].at, since)
    end = min(merged or until, until)
    if merged is None and seen[-1].status in OVER:
        end = min(seen[-1].at, until)
    if end <= start:
        return None
    said = [one for one in project.said if one.number in numbers]
    marks = [one for one in project.marks if one.slug == slug]
    spans = _cut(_changes(seen, said, marks), start, end, _opened(project, slug, seen, approved))
    spans = _overlay(spans, _carved(project, slug, seen))
    depends = next((one.depends for one in reversed(seen) if one.depends), ())
    done = merged if merged and merged <= until else None
    return Row(project.name, slug, approved, done, spans, depends)


def _opened(project: Project, slug: str, seen: list[Sighting], approved: datetime | None) -> str:
    """Return the record that says when the row's clock starts: its approval, or its first line."""
    if approved is not None:
        return f"{project.name} approved column or item line of {slug}: {approved.isoformat()}"
    return seen[0].source


def _merged(
    project: Project,
    slug: str,
    numbers: set[str],
    seen: list[Sighting],
    merges: dict[str, datetime],
) -> datetime | None:
    found = [merges[one] for one in numbers if one in merges]
    if found:
        return min(found)
    if slug in project.merged:
        return project.merged[slug][0]
    return next((one.at for one in seen if one.status == "merged"), None)


Change = tuple[datetime, str, str]


def _changes(seen: list[Sighting], said: list[Said], marks: list[Mark]) -> list[Change]:
    """Return each time the row's class changed, from its sightings, `jmerge`'s lines and its
    item's marks, each with the record that said it. A table's line sets the row's state; a
    `jmerge` line or a mark changes only why a pull request waits, until the next table line."""
    every: list[tuple[datetime, int, Sighting | Said | Mark]] = [(one.at, 0, one) for one in seen]
    every += [(one.at, 1, one) for one in said]
    every += [(one.at, 2, one) for one in marks]
    status, checks, why, merger = "", "", "", ""
    found: list[Change] = []
    for at, _, one in sorted(every, key=lambda mark: (mark[0], mark[1])):
        if isinstance(one, Sighting):
            status, checks, why = one.status, one.checks, one.why
        elif isinstance(one, Said):
            merger = f"{one.verdict}: {one.why}" if one.verdict == "hold" else one.why
            if status != "pr":
                continue
            why = merger
        elif status == "pr":
            why = one.why or merger or why
        else:
            continue
        if status in OVER:
            found.append((at, "", one.source))
            continue
        found.append((at, state_class(status, checks, why), one.source))
    return found


def _cut(changes: list[Change], start: datetime, end: datetime, opened: str) -> list[Span]:
    spans: list[Span] = []
    current, at, source = NO_RECORD, start, opened
    for moment, what, said in changes:
        if moment <= start:
            current, source = what, said
            continue
        if moment >= end:
            break
        if what != current:
            if current:
                spans.append(Span(at, moment, current, source))
            current, at, source = what, moment, said
    if current:
        spans.append(Span(at, end, current, source))
    return [one for one in spans if one.end > one.start]


def _carved(project: Project, slug: str, seen: list[Sighting]) -> list[Span]:
    threads = {one.thread for one in seen if one.thread}
    said = f"{project.name} events.jsonl"
    carved = [
        Span(one.at, one.until, "account cap", f"{said} {one.at.isoformat()} stall")
        for one in project.caps
        if one.slug == slug
    ]
    for wait in project.slots:
        if wait.minutes and (wait.slug == slug or wait.thread in threads):
            began = wait.at - timedelta(minutes=wait.minutes)
            source = f"{said} {wait.at.isoformat()} slot-wake"
            carved.append(Span(began, wait.at, "test slot", source))
    return carved


def _overlay(spans: list[Span], carved: list[Span]) -> tuple[Span, ...]:
    """Lay each carved span over the spans of `crew at work` it overlaps."""
    for cut in sorted(carved, key=lambda one: one.start):
        made = []
        for one in spans:
            if one.what != "crew at work" or cut.end <= one.start or cut.start >= one.end:
                made.append(one)
                continue
            middle = Span(max(one.start, cut.start), min(one.end, cut.end), cut.what, cut.source)
            made += [
                part
                for part in (Span(one.start, middle.start, one.what, one.source), middle)
                if part.end > part.start
            ]
            if middle.end < one.end:
                made.append(Span(middle.end, one.end, one.what, one.source))
        spans = made
    return tuple(spans)


def rows(
    projects: Iterable[Project], since: datetime, until: datetime, merges: dict[str, dict]
) -> list[Row]:
    """Return every row with time in the window, of every project."""
    found = []
    for project in projects:
        for slug in project.sightings:
            row = row_spans(project, slug, since, until, merges.get(project.name, {}))
            if row is not None:
                found.append(row)
    return found


def pareto(found: Iterable[Row]) -> list[dict]:
    """Return each class of waiting by hours lost, the most first, with its share, the running
    share, how many rows waited on it, and the row that waited on it longest."""
    hours: Counter[str] = Counter()
    who: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in found:
        for span in row.spans:
            if span.what not in WORKING:
                hours[span.what] += span.hours
                who[span.what][f"{row.project}/{row.slug}"] += span.hours
    total = sum(hours.values()) or 1.0
    ranked, running = [], 0.0
    for what, lost in hours.most_common():
        running += lost
        ranked.append(
            {
                "class": what,
                "hours": round(lost, 1),
                "share": round(lost / total, 3),
                "cumulative": round(running / total, 3),
                "rows": len(who[what]),
                "worst_row": who[what].most_common(1)[0][0],
                "worst_row_hours": round(who[what].most_common(1)[0][1], 1),
                "unexplained": what in UNEXPLAINED,
                "no_record": what == NO_RECORD,
            }
        )
    return ranked


def lead_times(found: Iterable[Row], spans: bool = False) -> dict:
    """Return the approved-to-merged times of the rows that merged in the window, and with
    `spans` each row's spans, each with the record that opened it."""
    done = [one for one in found if one.merged is not None and one.approved is not None]
    whole = [(one.merged - one.approved).total_seconds() / 3600 for one in done]  # type: ignore[operator]
    return {
        "merged": len(done),
        "median_hours": _quantile(whole, 0.5),
        "p85_hours": _quantile(whole, 0.85),
        "working_hours": round(sum(one.hours(True) for one in done), 1),
        "waiting_hours": round(sum(one.hours(False) for one in done), 1),
        "rows": [
            {
                "project": one.project,
                "slug": one.slug,
                "approved": one.approved.isoformat(),  # type: ignore[union-attr]
                "merged": one.merged.isoformat(),  # type: ignore[union-attr]
                "working_hours": round(one.hours(True), 1),
                "waiting_hours": round(one.hours(False), 1),
                "top_wait": _top(one)[0],
                "top_wait_hours": round(_top(one)[1], 1),
            }
            | ({"spans": [_span(span) for span in one.spans]} if spans else {})
            for one in sorted(done, key=lambda row: row.hours(), reverse=True)
        ],
    }


def _top(row: Row) -> tuple[str, float]:
    waits: Counter[str] = Counter()
    for span in row.spans:
        if span.what not in WORKING:
            waits[span.what] += span.hours
    return waits.most_common(1)[0] if waits else ("", 0.0)


def _span(span: Span) -> dict:
    return {
        "start": span.start.isoformat(),
        "end": span.end.isoformat(),
        "class": span.what,
        "hours": round(span.hours, 2),
        "source": span.source,
    }


ORDERING = "ordering"
NOT_KNOWN = "behind a row with no record in the window"
NOT_APPROVED = "the row ahead was not yet approved"
MERGED_AHEAD = "behind rows already merged"
DEPTH = 12


def behind(found: Iterable[Row]) -> dict:
    """Return what the `ordering` hours waited on: each span is shared out evenly over the rows
    it depends on that had not merged, and each share takes the class of that row over the same
    time, followed on through that row's own `ordering` to the head of the chain. A row it
    depends on with no record in the window is said as such, and so is a row with no `depends`
    known."""
    by_key = {(one.project, one.slug): one for one in found}
    blame: Counter[str] = Counter()
    links: list[int] = []
    for row in by_key.values():
        for span in row.spans:
            if span.what == ORDERING:
                links.append(_follow(by_key, row, span.start, span.end, 1.0, blame, 0, set()))
    total = sum(blame.values())
    return {
        "hours": round(total, 1),
        "chains": sum(1 for one in links if one > 1),
        "longest_chain": max(links, default=0),
        "heads": [
            {"class": what, "hours": round(lost, 1), "share": round(lost / total, 3)}
            for what, lost in blame.most_common()
        ],
    }


def _follow(
    by_key: dict[tuple[str, str], Row],
    row: Row,
    start: datetime,
    end: datetime,
    weight: float,
    blame: Counter[str],
    depth: int,
    path: set[str],
) -> int:
    """Share `weight` of `start` to `end` of `row`'s ordering out over the rows it waited on, and
    return how many links the longest chain from it has. The time is cut where a row ahead
    merges: in each piece the rows ahead are those not merged yet, each with an even share."""
    if not row.depends:
        blame["no depends known"] += (end - start).total_seconds() / 3600 * weight
        return 1
    ahead = [(slug, by_key.get((row.project, slug))) for slug in row.depends]
    cuts = sorted(
        {start, end}
        | {one.merged for _, one in ahead if one and one.merged and start < one.merged < end}
    )
    deepest = 1
    for a, b in itertools.pairwise(cuts):
        hours = (b - a).total_seconds() / 3600 * weight
        open_ = [
            (slug, one)
            for slug, one in ahead
            if one is None or one.merged is None or one.merged > a
        ]
        if not open_:
            blame[MERGED_AHEAD] += hours
            continue
        share = weight / len(open_)
        for slug, one in open_:
            if one is None or slug in path or depth >= DEPTH:
                blame[NOT_KNOWN if one is None else "a loop of depends"] += hours / len(open_)
                continue
            covered = 0.0
            for span in one.spans:
                x, y = max(span.start, a), min(span.end, b)
                if y <= x:
                    continue
                part = (y - x).total_seconds() / 3600 * share
                covered += part
                if span.what == ORDERING:
                    link = _follow(by_key, one, x, y, share, blame, depth + 1, path | {row.slug})
                    deepest = max(deepest, link + 1)
                else:
                    blame[span.what] += part
                    deepest = max(deepest, 2)
            if hours / len(open_) - covered > 1e-9:
                blame[NOT_APPROVED] += hours / len(open_) - covered
    return deepest


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q * 100) - 1], 1)


def intervals(moments: Iterable[datetime], gap: timedelta = GAP) -> list[tuple[datetime, datetime]]:
    """Join moments no more than `gap` apart into spans, each one pass long past its last."""
    joined: list[list[datetime]] = []
    for at in sorted(moments):
        if joined and at - joined[-1][1] <= gap:
            joined[-1][1] = at
        else:
            joined.append([at, at])
    return [(first, last + PASS) for first, last in joined]


def union(spans: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    joined: list[list[datetime]] = []
    for start, end in sorted(spans):
        if joined and start <= joined[-1][1]:
            joined[-1][1] = max(joined[-1][1], end)
        else:
            joined.append([start, end])
    return [(a, b) for a, b in joined]


def _hours(spans: Iterable[tuple[datetime, datetime]]) -> float:
    return round(sum((b - a).total_seconds() for a, b in spans) / 3600, 1)


def no_room(lines: list[Line], since: datetime, until: datetime) -> dict:
    """Return how long the machine had no room for a launch, and why, from the journal."""
    by: defaultdict[str, list[datetime]] = defaultdict(list)
    slugs: set[str] = set()
    for line in lines:
        found = re.match(r"^wait (\S+): no room: (.*)$", line.text)
        if found and since <= line.at <= until:
            slugs.add(found[1])
            by[_room_why(found[2])].append(line.at)
    spans = {why: intervals(at) for why, at in by.items()}
    every = union(span for each in spans.values() for span in each)
    return {
        "hours": _hours(every),
        "spans": len(every),
        "rows_held": len(slugs),
        "by_reason": {why: _hours(each) for why, each in sorted(spans.items())},
        "longest": [
            {"start": a.isoformat(), "end": b.isoformat(), "hours": _hours([(a, b)])}
            for a, b in sorted(every, key=lambda span: span[0] - span[1])[:5]
        ],
    }


def _room_why(said: str) -> str:
    for pattern, name in (
        (r"load", "load over 85% of the cores"),
        (r"memory|GB|available", "memory"),
        (r"pressure", "memory pressure"),
        (r"did not run", "jgauge room did not run"),
    ):
        if re.search(pattern, said):
            return name
    return "other"


def caps(projects: Iterable[Project], lines: list[Line], since: datetime, until: datetime) -> dict:
    """Return how long each account was capped, and how many rows a cap held."""
    every: list[Cap] = [one for project in projects for one in project.caps]
    for line in lines:
        found = re.match(r"^capped (\S+): (\S+) is capped until (\S+)", line.text)
        if found:
            end = when(found[3])
            if end and end > line.at:
                every.append(Cap(line.at, end, found[1], (found[2],)))
    by: defaultdict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    slugs = set()
    for cap in every:
        start, end = max(cap.at, since), min(cap.until, until)
        if end > start:
            slugs.add(cap.slug)
            for account in cap.accounts:
                by[account].append((start, end))
    whole = union(span for each in by.values() for span in each)
    return {
        "hours_any": _hours(whole),
        "rows_held": len(slugs),
        "by_account": {name: _hours(union(each)) for name, each in sorted(by.items())},
    }


def slots(projects: Iterable[Project], since: datetime, until: datetime) -> dict:
    waits: list[SlotWait] = [
        one for project in projects for one in project.slots if since <= one.at <= until
    ]
    pool = [m for project in projects for at, m in project.pool if since <= at <= until]
    minutes = [one.minutes for one in waits]
    return {
        "test_slot_waits": len(waits),
        "test_slot_hours": round(sum(minutes) / 60, 1),
        "test_slot_longest_min": max(minutes, default=0),
        "review_pool_waits": len(pool),
        "review_pool_hours": round(sum(pool) / 60, 1),
    }


def jbus_down(lines: list[Line], since: datetime, until: datetime) -> dict:
    """Return the passes that failed, and the gaps of more than ten minutes between passes."""
    starts = sorted(
        line.at for line in lines if line.text.startswith("Starting jbus") and since <= line.at
    )
    failed = [
        line.at
        for line in lines
        if since <= line.at <= until
        and (line.text.startswith("Failed to start jbus") or line.text.startswith("pass failed"))
    ]
    late = [line for line in lines if since <= line.at <= until]
    github = [line.at for line in late if "could not ask GitHub" in line.text]
    webhook = [line.at for line in late if line.text.startswith("wake failed")]
    gaps = [(a, b) for a, b in itertools.pairwise(starts) if b - a > timedelta(minutes=10)]
    return {
        "first_pass": starts[0].isoformat() if starts else None,
        "passes": len(starts),
        "failed_passes": len(failed),
        "failed_hours": _hours(intervals(failed)),
        "gaps_over_10_min": len(gaps),
        "gap_hours": _hours(gaps),
        "github_unreachable_hours": _hours(intervals(github)),
        "webhook_failures": len(webhook),
    }


def main_red(found_runs: list[Run], found_rows: list[Row], merges: dict[str, dict]) -> dict:
    """Return, for each repo, how long main was red on its gate workflow (the workflow with the
    most runs on pushes to main), and what that held up: the rows whose wait was `main red`,
    their hours, and the pull requests that merged while it was red. Each other workflow of
    main's pushes is measured the same way under `by_workflow`, since one that stays red is a
    red nobody's rule reads. Each span names the run that turned it red and the run that ended it.

    A failed run that ended within `NO_JOB` of its start ran no job: GitHub started none, as on
    a failed payment or a spent limit. Such a run turns main neither red nor green. The time
    until the next run that did run a job is counted as `no_job_hours`, CI that did not run."""
    by_repo: defaultdict[str, list[Run]] = defaultdict(list)
    for run in found_runs:
        if run.event == "push" and run.branch == "main":
            by_repo[run.repo].append(run)
    said: dict[str, dict] = {}
    for repo, pushed in sorted(by_repo.items()):
        counted = Counter(one.workflow for one in pushed)
        gate = counted.most_common(1)[0][0]
        flows = {name: _red(pushed, name) for name in sorted(counted)}
        red, idle, ordered = flows[gate]
        spans = [(a, b) for a, b, *_ in red]
        merged = [at for at in merges.get(repo, {}).values() if any(a <= at <= b for a, b in spans)]
        said[repo] = {
            "gate": gate,
            "red_hours": _hours(spans),
            "red_spans": len(red),
            "merges_while_red": len(merged),
            "no_job_hours": _hours(idle),
            "no_job_runs": sum(1 for one in ordered if _no_job(one)),
            "spans": [
                {"start": a.isoformat(), "end": b.isoformat(), "red_run": r, "green_run": g}
                for a, b, r, g in red
            ],
            "by_workflow": {
                name: {
                    "red_hours": _hours([(a, b) for a, b, *_ in each[0]]),
                    "red_spans": len(each[0]),
                    "still_red": bool(each[0]) and each[0][-1][3] is None,
                    "no_job_hours": _hours(each[1]),
                    "no_job_runs": sum(1 for one in each[2] if _no_job(one)),
                    "runs": len(each[2]),
                }
                for name, each in flows.items()
            },
        }
    held = [one for one in found_rows if any(span.what == "main red" for span in one.spans)]
    return {
        "repos": said,
        "rows_held": len(held),
        "row_hours_held": round(
            sum(span.hours for one in held for span in one.spans if span.what == "main red"), 1
        ),
    }


RedSpan = tuple[datetime, datetime, int, int | None]


def _red(pushed: list[Run], workflow: str) -> tuple[list[RedSpan], list[tuple], list[Run]]:
    """Return when `workflow` was red on main, each span with the run that turned it red and
    the run that turned it green (None while it stays red), when CI ran no job, and the runs,
    read in the order the runs ended, since a run that ends last says what main is now."""
    ordered = sorted(
        (one for one in pushed if one.workflow == workflow and one.updated),
        key=lambda one: (one.updated, one.created),
    )
    red: list[RedSpan] = []
    idle: list[tuple[datetime, datetime]] = []
    start: Run | None = None
    down: datetime | None = None
    for run in ordered:
        if _no_job(run):
            down = down or run.updated
            continue
        if down is not None:
            idle.append((down, run.updated))  # type: ignore[arg-type]
            down = None
        if run.conclusion == "failure" and start is None:
            start = run
        elif run.conclusion == "success" and start is not None:
            red.append((start.updated, run.updated, start.id, run.id))  # type: ignore[arg-type]
            start = None
    if start is not None:
        red.append((start.updated, ordered[-1].updated, start.id, None))  # type: ignore[arg-type]
    if down is not None:
        idle.append((down, ordered[-1].updated))
    return red, idle, ordered


NO_JOB = timedelta(seconds=15)


def _no_job(run: Run) -> bool:
    began = run.started or run.created
    return run.conclusion == "failure" and run.updated is not None and run.updated - began < NO_JOB


def ci(found_runs: list[Run]) -> dict:
    """Return, for each repo, its runs, their conclusions, reruns, and the queue and run time
    of their jobs, on GitHub's runners and on self-hosted ones. A run's own queue, from its
    creation to its start, is there without `--jobs`, for the runs of one attempt."""
    said = {}
    by: defaultdict[str, list[Run]] = defaultdict(list)
    for run in found_runs:
        by[run.repo].append(run)
    for repo, each in sorted(by.items()):
        ends = Counter(one.conclusion for one in each)
        queued = [q for one in each for q in one.queued]
        hosted = [q for one in each for q, h in zip(one.queued, one.hosted, strict=True) if h]
        ran = [r for one in each for r in one.ran]
        waited = [one.waited for one in each if one.waited is not None]
        said[repo] = {
            "runs": len(each),
            "failure": ends.get("failure", 0),
            "cancelled": ends.get("cancelled", 0),
            "reruns": sum(1 for one in each if one.attempt > 1),
            "jobs": len(queued),
            "queue_hours": round(sum(queued) / 3600, 1),
            "queue_median_s": _quantile(queued, 0.5),
            "queue_p90_s": _quantile(queued, 0.9),
            "queue_self_hosted_hours": round((sum(queued) - sum(hosted)) / 3600, 1),
            "run_queue_hours": round(sum(waited) / 3600, 1),
            "run_queue_median_s": _quantile(waited, 0.5),
            "run_queue_p90_s": _quantile(waited, 0.9),
            "run_hours": round(sum(ran) / 3600, 1),
            "run_median_s": _quantile(ran, 0.5),
        }
    return said


def ledger_jobs(jobs: dict[str, list[dict]], since: datetime, until: datetime) -> dict:
    """Return how long the jobs `jbus ci` kept in each project's `ci.jsonl` waited for a runner,
    by the runner's kind: a queue time that costs no call to GitHub."""
    said: dict[str, dict] = {}
    for name, kept in sorted(jobs.items()):
        inside = [
            one
            for one in kept
            if (made := when(one.get("created") or "")) is not None and since <= made <= until
        ]
        if not inside:
            continue
        found: dict[str, Any] = {"jobs": len(inside)}
        for kind in sorted({str(one.get("kind") or "?") for one in inside}):
            mine = [one for one in inside if str(one.get("kind") or "?") == kind]
            waited = [
                (began - made).total_seconds()
                for one in mine
                if (made := when(one.get("created") or ""))
                and (began := when(one.get("started") or ""))
            ]
            found[kind] = {
                "jobs": len(mine),
                "queue_hours": round(sum(waited) / 3600, 1),
                "queue_median_s": _quantile(waited, 0.5),
                "queue_p90_s": _quantile(waited, 0.9),
                "cancelled_waiting": sum(
                    1
                    for one in mine
                    if one.get("conclusion") == "cancelled" and not one.get("started")
                ),
            }
        made_at = [when(one["created"]) for one in inside]
        found["from"] = min(made_at).isoformat()  # type: ignore[type-var,union-attr]
        found["to"] = max(made_at).isoformat()  # type: ignore[type-var,union-attr]
        said[name] = found
    return said


def pages(projects: Iterable[Project], since: datetime, until: datetime) -> dict:
    """Return how many events paged the owner (loud `user`), by kind and by project."""
    counted: Counter[str] = Counter()
    by_project: Counter[str] = Counter()
    for project in projects:
        for at, kind in project.pages:
            if since <= at <= until:
                counted[kind] += 1
                by_project[project.name] += 1
    return {"total": sum(counted.values()), "by_kind": dict(counted.most_common())} | {
        "by_project": dict(by_project.most_common())
    }
