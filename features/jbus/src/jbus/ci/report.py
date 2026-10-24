"""Write the week's report of the nine targets, `reports/ci-week-<date>.md` in a project's
home, and send the one alert for a missed target.

The report gives every number with how it counts (`Number.how`), the period, and what the
counts are based on: the jobs, local and hosted apart, and how many jobs were cancelled
while they waited. jbus sends no alert for a week with every target met, or with no data.
For a week that missed a target it sends one `alert` event, which names each missed target.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

import jsettings
from jbus import Config, Project, alert, passes
from jbus.ci import numbers


def missed(nine: list[numbers.Number]) -> list[numbers.Number]:
    return [one for one in nine if one.met is False]


def _counts(jobs: list[dict[str, Any]], start: datetime, end: datetime) -> list[str]:
    inside = [j for j in jobs if start <= numbers.time(j["created"]) < end]
    lines = []
    for kind in ("local", "hosted"):
        ours = [j for j in inside if j["kind"] == kind]
        queued = [j for j in ours if j["conclusion"] == "cancelled" and not j.get("started")]
        lines.append(
            f"- {kind}: {len(ours)} jobs, of which {len(queued)} were cancelled while they waited"
        )
    return lines


def body(
    facts: numbers.Facts,
    nine: list[numbers.Number],
    start: datetime,
    end: datetime,
    zone: tzinfo,
    user: jsettings.Settings,
) -> str:
    days = numbers.day_windows(end, max(1, round((end - start) / timedelta(days=1))), zone)
    red = [f"- {day}: {numbers.mainred(facts, a, b).shown}" for day, a, b in days]
    rows = [
        f"| {one.name} | {one.shown} | {one.hosted or '-'} | {one.target} | "
        f"{'missed' if one.met is False else 'met' if one.met else 'no data'} |"
        for one in nine
    ]
    how = [f"- **{one.name}** (n = {one.n}): {one.how}" for one in nine]
    return "\n".join(
        [
            f"# CI, the week to {user.stamp(end)}",
            "",
            f"Period: {user.stamp(start)} to {user.stamp(end)}. Job level only: a job counts once,"
            " a run never. Local and hosted runners are counted apart, and the local runner's"
            " figure is the one the target is held to. A job cancelled while it waited is"
            " counted as a job.",
            "",
            "| target | local | hosted | held to | |",
            "| --- | --- | --- | --- | --- |",
            *rows,
            "",
            "## Counted",
            "",
            *_counts(facts.jobs, start, end),
            "",
            "## How each number was counted",
            "",
            *how,
            "",
            "## Main red, by day",
            "",
            *red,
            "",
        ]
    )


def write(home: Path, text: str, now: datetime, user: jsettings.Settings) -> Path:
    path = home / "reports" / f"ci-week-{user.day(now)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def escalate(
    config: Config,
    project: Project,
    nine: list[numbers.Number],
    path: Path,
    now: datetime,
    say: Any,
) -> int:
    """Alert the project once for the week if it missed a target. The alert's key is the
    week's report, so a second run on the same day sends no second alert."""
    late = missed(nine)
    if not late:
        say("ci: every target met or without data, no alert")
        return 0
    which = "; ".join(f"{one.name} {one.shown} (held to {one.target})" for one in late)
    line = f"ci week {config.user.day(now)}: missed {which}. Report: {path}"
    run = passes.Pass(config, project, now, say)
    run.box.send("", "alert", line, key=f"ci-week-{config.user.day(now)}")
    alert.flush(run)
    say(f"ci: alert for {len(late)} missed")
    return 0
