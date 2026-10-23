"""The numbers of a window, as one dict (`measure`) and as the text `jbus flow` prints (`text`).

A row-hour is an hour of one row's time: two rows that wait the same hour count two. The
Pareto ranks the reasons rows waited by the row-hours each one cost, cut to the window, for
every approved row and not only for the rows that merged. The value stream adds the hours the
crews worked, so that the stages compare.

What the records do not cover is said too: the part of the window before a project's first
event, the time no pass ran, and the waiting row-hours whose state `rows.classify` could not
place.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from jbus.flow import machine, rows, runs

TOP = 12


@dataclass
class Records:
    """What `measure` reads: each project's rows (`tables`) and first event, the journal, and
    each repo's Actions runs (`actions`), or why GitHub was not asked (`unasked`), and the
    jobs `jbus ci` kept (`jobs`)."""

    since: datetime
    until: datetime
    tables: dict[str, list[rows.Row]] = field(default_factory=dict)
    first: dict[str, datetime | None] = field(default_factory=dict)
    journal: machine.Machine = field(default_factory=machine.Machine)
    actions: dict[str, runs.Runs] = field(default_factory=dict)
    unasked: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def hours(spans: Iterable[tuple[datetime, datetime, Any]]) -> float:
    """Return the hours the stretches cover, each hour once where two overlap."""
    total, reach = 0.0, None
    for start, end, *_ in sorted(spans, key=lambda one: one[0]):
        if reach is not None and start < reach:
            start = reach
        if end > start:
            total += (end - start).total_seconds() / 3600
            reach = end
    return total


def shown(when: datetime | None) -> str:
    return when.astimezone().strftime("%Y-%m-%d %H:%M %Z") if when else "none"


def lead(found: Records) -> dict[str, Any]:
    """Return the merged rows' time from approved to merged, split into working and waiting."""
    merged = [
        row
        for kept in found.tables.values()
        for row in kept
        if row.end == "merged" and row.ended and found.since <= row.ended <= found.until
    ]
    each = []
    for row in merged:
        cut = [span for _, span in rows.clip([row], found.since, found.until)]
        working = sum(span.hours for span in cut if span.stage == rows.WORK)
        waited: dict[str, float] = {}
        for span in cut:
            if span.stage != rows.WORK:
                waited[span.name] = waited.get(span.name, 0) + span.hours
        total = sum(span.hours for span in cut)
        worst = max(waited, key=waited.__getitem__) if waited else ""
        each.append(
            {
                "project": row.project,
                "slug": row.slug,
                "approved": shown(row.approved),
                "merged": shown(row.ended),
                "hours": round(total, 2),
                "working": round(working, 2),
                "waiting": round(total - working, 2),
                "worst": worst,
                "worst_hours": round(waited.get(worst, 0.0), 2),
            }
        )
    each.sort(key=lambda one: one["hours"], reverse=True)
    days: dict[str, int] = {}
    for row in merged:
        day = row.ended.astimezone().strftime("%Y-%m-%d") if row.ended else ""
        days[day] = days.get(day, 0) + 1
    totals = [one["hours"] for one in each]
    worked = sum(one["working"] for one in each)
    return {
        "merged": len(each),
        "median_hours": round(statistics.median(totals), 2) if totals else None,
        "p90_hours": round(sorted(totals)[int(0.9 * (len(totals) - 1))], 2) if totals else None,
        "working_share": round(worked / sum(totals), 3) if sum(totals) else None,
        "per_day": dict(sorted(days.items())),
        "rows": each,
    }


def pareto(cut: list[tuple[rows.Row, rows.Span]]) -> list[dict[str, Any]]:
    """Return the wait reasons by row-hours, the largest first, with the cumulative share."""
    by: dict[tuple[str, str], float] = {}
    who: dict[tuple[str, str], dict[str, float]] = {}
    for row, span in cut:
        if span.stage == rows.WORK:
            continue
        key, slug = (span.stage, span.name), f"{row.project}/{row.slug}"
        by[key] = by.get(key, 0) + span.hours
        each = who.setdefault(key, {})
        each[slug] = each.get(slug, 0) + span.hours
    total = sum(by.values())
    ranked, running = [], 0.0
    for key in sorted(by, key=by.__getitem__, reverse=True):
        running += by[key]
        ranked.append(
            {
                "stage": key[0],
                "reason": key[1],
                "hours": round(by[key], 1),
                "share": round(by[key] / total, 3) if total else 0,
                "cumulative": round(running / total, 3) if total else 0,
                "rows": len(who[key]),
                "median_row_hours": round(statistics.median(who[key].values()), 2),
                "worst_row": max(who[key], key=who[key].__getitem__),
            }
        )
    return ranked


def waits(jobs: list[dict[str, Any]], since: datetime, until: datetime) -> dict[str, Any]:
    """Return how long the jobs `jbus ci` kept waited for a runner, by the runner's kind."""
    inside = [
        one
        for one in jobs
        if (made := runs.when(one.get("created"))) is not None and since <= made <= until
    ]
    found: dict[str, Any] = {"jobs": len(inside)}
    for kind in sorted({str(one.get("kind") or "?") for one in inside}):
        mine = [one for one in inside if str(one.get("kind") or "?") == kind]
        queued = [
            waited
            for one in mine
            if (waited := runs.minutes(one.get("created"), one.get("started"))) is not None
        ]
        found[kind] = {
            "jobs": len(mine),
            "queue": runs.spread(queued),
            "cancelled_waiting": sum(
                1 for one in mine if one.get("conclusion") == "cancelled" and not one.get("started")
            ),
        }
    if inside:
        found["from"] = shown(min(runs.when(one["created"]) for one in inside))
        found["to"] = shown(max(runs.when(one["created"]) for one in inside))
    return found


def measure(found: Records) -> dict[str, Any]:
    """Return every number of the window."""
    window = (found.until - found.since).total_seconds() / 3600
    cut = rows.clip(
        [row for kept in found.tables.values() for row in kept], found.since, found.until
    )
    stages: dict[str, float] = {}
    for _, span in cut:
        stages[span.stage] = stages.get(span.stage, 0) + span.hours
    waiting = sum(spent for stage, spent in stages.items() if stage != rows.WORK)
    held = [(row, span) for row, span in cut if span.stage == "main"]
    jour = found.journal
    room: dict[str, list[tuple[datetime, datetime, str]]] = {}
    for one in jour.no_room:
        room.setdefault(one[2], []).append(one)
    return {
        "window": {"since": shown(found.since), "until": shown(found.until), "hours": window},
        "records": {
            "events": {name: shown(first) for name, first in found.first.items()},
            "events_missing_hours": {
                name: round((min(first, found.until) - found.since).total_seconds() / 3600, 1)
                if first and first > found.since
                else (round(window, 1) if first is None else 0.0)
                for name, first in found.first.items()
            },
            "journal_first_pass": shown(jour.first),
            "journal_missing_hours": round(
                (
                    (min(jour.first, found.until) if jour.first else found.until) - found.since
                ).total_seconds()
                / 3600,
                1,
            ),
            "journal_passes": jour.passes,
            "github": {name: f"{kept.runs} runs" for name, kept in found.actions.items()},
            "github_not_asked": found.unasked,
        },
        "lead": lead(found),
        "stages": {
            stage: round(spent, 1)
            for stage, spent in sorted(stages.items(), key=lambda one: one[1], reverse=True)
        },
        "pareto": pareto(cut),
        "main_red": {
            "repos": {
                name: {
                    "hours": round(hours(kept.red), 1),
                    "by_workflow": {
                        flow: round(hours([one for one in kept.red if one[2] == flow]), 1)
                        for flow in sorted({one[2] for one in kept.red})
                    },
                    "stretches": len(kept.red),
                    "pull_request_runs_failed_while_red": kept.ran_red,
                }
                for name, kept in found.actions.items()
            },
            "rows_held": len({(row.project, row.slug) for row, _ in held}),
            "row_hours_held": round(sum(span.hours for _, span in held), 1),
        },
        "machine": {
            "no_room_hours": round(hours(jour.no_room), 1),
            "by_why": {
                why: {"hours": round(hours(kept), 1), "passes": len(kept)}
                for why, kept in sorted(room.items(), key=lambda one: -hours(one[1]))
            },
            "rows_told_no_room": dict(sorted(jour.waited.items(), key=lambda one: -one[1])),
            "jbus_not_running_hours": round(hours(jour.down), 1),
            "passes_failed": jour.failed,
            "passes_github_unreachable": jour.github,
            "wakes_failed": dict(sorted(jour.wakes.items(), key=lambda one: -one[1])),
        },
        "jobs": {name: waits(kept, found.since, found.until) for name, kept in found.jobs.items()},
        "ci": {
            name: {
                "runs": kept.runs,
                "failed": kept.failed,
                "cancelled": kept.cancelled,
                "rerun_runs": kept.rerun,
                "rerun_attempts": kept.attempts,
                "queue": runs.spread(kept.queued),
                "run": runs.spread(kept.ran),
            }
            for name, kept in found.actions.items()
        },
        "unexplained": {
            "row_hours": round(stages.get(rows.UNEXPLAINED, 0.0), 1),
            "waiting_row_hours": round(waiting, 1),
            "share": round(stages.get(rows.UNEXPLAINED, 0.0) / waiting, 3) if waiting else None,
        },
    }


def text(numbers: dict[str, Any], every: bool = False) -> str:
    """Return the numbers as the lines `jbus flow` prints."""
    say: list[str] = []
    window, kept = numbers["window"], numbers["records"]
    say.append(f"jbus flow: {window['since']} to {window['until']} ({window['hours']:.1f} h)")
    say.append("")
    say.append("Records")
    for name, first in kept["events"].items():
        missing = kept["events_missing_hours"][name]
        say.append(f"  {name}: events from {first}, {missing} h of the window before them")
    say.append(
        f"  journal: {kept['journal_passes']} passes, the first {kept['journal_first_pass']}"
    )
    for name, said in kept["github"].items():
        say.append(f"  GitHub {name}: {said}")
    for name, why in kept["github_not_asked"].items():
        say.append(f"  GitHub {name}: not asked, {why}")
    led = numbers["lead"]
    say.append("")
    say.append("Approved to merged")
    if led["merged"]:
        say.append(
            f"  {led['merged']} rows merged: median {led['median_hours']} h, p90 "
            f"{led['p90_hours']} h, working {led['working_share']:.0%} of their time"
        )
        for one in led["rows"] if every else led["rows"][:TOP]:
            say.append(
                f"  {one['project']}/{one['slug']}: {one['hours']} h, working {one['working']} h,"
                f" waiting {one['waiting']} h, most on {one['worst'] or 'nothing'}"
                f" ({one['worst_hours']} h)"
            )
        say.append(
            "  merged a day: " + ", ".join(f"{day} {n}" for day, n in led["per_day"].items())
        )
        if not every and led["merged"] > TOP:
            say.append(f"  ({led['merged'] - TOP} more with --rows)")
    else:
        say.append("  no row merged in the window")
    say.append("")
    say.append("Value stream, row-hours by stage")
    total = sum(numbers["stages"].values())
    for stage, spent in numbers["stages"].items():
        share = spent / total if total else 0
        say.append(f"  {stage}: {spent} h ({share:.0%})")
    say.append("")
    say.append("Wait reasons by row-hours lost")
    for rank, one in enumerate(numbers["pareto"], 1):
        say.append(
            f"  {rank}. {one['reason']} [{one['stage']}]: {one['hours']} h, {one['share']:.0%}"
            f" (cumulative {one['cumulative']:.0%}), {one['rows']} rows, median"
            f" {one['median_row_hours']} h a row, most {one['worst_row']}"
        )
    red = numbers["main_red"]
    say.append("")
    say.append("Main red")
    for name, one in red["repos"].items():
        flows = ", ".join(f"{flow} {spent} h" for flow, spent in one["by_workflow"].items())
        say.append(
            f"  {name}: red {one['hours']} h in {one['stretches']} stretches"
            f"{f' ({flows})' if flows else ''}, {one['pull_request_runs_failed_while_red']}"
            " pull request runs failed while it was red"
        )
    say.append(f"  held up {red['rows_held']} rows for {red['row_hours_held']} row-hours")
    room = numbers["machine"]
    say.append("")
    say.append("Machine")
    say.append(f"  no room or no launch: {room['no_room_hours']} h")
    for why, one in room["by_why"].items():
        say.append(f"    {why}: {one['hours']} h over {one['passes']} passes")
    say.append(f"  jbus ran no pass, or the pass failed: {room['jbus_not_running_hours']} h")
    say.append(
        f"  passes that failed: {room['passes_failed']}, passes that could not ask GitHub:"
        f" {room['passes_github_unreachable']}"
    )
    for why, times in room["wakes_failed"].items():
        say.append(f"  wake failed {why}: {times} passes")
    say.append("")
    say.append("CI runs")
    for name, one in numbers["ci"].items():
        say.append(
            f"  {name}: {one['runs']} runs, {one['failed']} failed, {one['cancelled']} cancelled,"
            f" {one['rerun_runs']} rerun ({one['rerun_attempts']} extra attempts)"
        )
        say.append(f"    queue: {one['queue']}")
        say.append(f"    run: {one['run']}")
    for name, one in numbers["jobs"].items():
        if not one["jobs"]:
            continue
        say.append(f"  {name} jobs kept by jbus ci, {one['from']} to {one['to']}:")
        for kind, seen in one.items():
            if isinstance(seen, dict):
                say.append(
                    f"    {kind}: {seen['jobs']} jobs, waited for a runner {seen['queue']},"
                    f" {seen['cancelled_waiting']} cancelled while waiting"
                )
    left = numbers["unexplained"]
    say.append("")
    say.append("Unexplained")
    share = f"{left['share']:.0%}" if left["share"] is not None else "no waiting"
    say.append(
        f"  {left['row_hours']} of {left['waiting_row_hours']} waiting row-hours have no known"
        f" reason ({share})"
    )
    missing = kept["events_missing_hours"]
    if any(missing.values()):
        say.append(
            "  window hours before a project's first event: "
            + ", ".join(f"{name} {spent} h" for name, spent in missing.items())
        )
    say.append(f"  window hours before the journal's first pass: {kept['journal_missing_hours']} h")
    say.append(f"  hours no pass ran or the pass failed: {room['jbus_not_running_hours']} h")
    return "\n".join(say) + "\n"
