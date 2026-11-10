"""The scorecard's page: each measure of `jbus.telemetry.measures` with its value now, its seven
days, its baseline and its state, as one static HTML file with no script and nothing fetched.

A band on top counts the measures worse than their baseline and names the worst three; a table a
group follows, in the order of `GROUPS`. The page reads only the store and shows only what the
measures themselves say, so it names no row, no path, no thread and no pull request: a query that
fails shows its error's kind alone, never its message.
"""

from __future__ import annotations

import html
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import jsettings
from jbus.telemetry import kpis, measures
from jbus.telemetry.measures import Lacks, Measure, Reading, Sql, State

GROUPS: tuple[measures.Group, ...] = ("flow", "cost", "quality", "attention", "machinery")
DAYS = 7
"""How many days a sparkline shows, today last."""
STATES: tuple[State, ...] = ("bad", "watch", "ok", "none")
"""The states from worst to best, the order the band ranks them in and the CLI counts them."""
WORDS: dict[State, str] = {
    "bad": "past its line",
    "watch": "worse than its baseline",
    "ok": "at or better than its baseline",
    "none": "no reading",
}
WINDOWS: dict[measures.Window, str] = {
    "hour": "the last hour",
    "day": "today so far",
    "72h": "the last 72 h",
    "week": "this week so far",
    "now": "now",
}


@dataclass(frozen=True)
class Line:
    """One measure on the page: its reading now and, for a measure of window `day`, its value on
    each of the last `DAYS` days, oldest first, each `None` where there is none."""

    measure: Measure
    reading: Reading
    days: tuple[float | None, ...] = ()


def lines(
    store: sqlite3.Connection, project: str, now: datetime, user: jsettings.Settings
) -> list[Line]:
    """Each measure of the registry read for `project` at `now`, with its days where it has any."""
    found = []
    for each in measures.MEASURES:
        reading = measures.read(store, each, project, now, user)
        found.append(Line(each, reading, _days(store, each, project, now, user, reading)))
    return found


def _days(
    store: sqlite3.Connection,
    measure: Measure,
    project: str,
    now: datetime,
    user: jsettings.Settings,
    reading: Reading,
) -> tuple[float | None, ...]:
    """The same part of each earlier day as today so far, so today's point compares with them."""
    if measure.window != "day" or not isinstance(measure.source, Sql):
        return ()
    owner = measures.MACHINE if measure.source.machine else project
    before: list[float | None] = []
    for back in range(DAYS - 1, 0, -1):
        begins, ends = measures.bounds("day", now, user, back)
        try:
            row = store.execute(
                measure.source.query, {"project": owner, "begins": begins, "ends": ends}
            ).fetchone()
        except sqlite3.Error:
            row = None
        before.append(None if row is None or row[0] is None else float(row[0]))
    return (*before, reading.value)


def counts(found: list[Line]) -> Counter[State]:
    return Counter(line.reading.state for line in found)


def line(found: list[Line]) -> str:
    """`3 bad, 5 watch, 20 ok, 13 none`."""
    seen = counts(found)
    return ", ".join(f"{seen[state]} {state}" for state in STATES)


def worst(found: list[Line]) -> list[Line]:
    """The measures worse than their baseline, worst first: past their line before worse than
    their baseline, a measure that wakes the user before one shown only, then the farthest from
    its baseline, as a share of it, or by its value where the baseline is 0."""
    return sorted(
        (each for each in found if each.reading.state in ("bad", "watch")),
        key=lambda each: (
            STATES.index(each.reading.state),
            each.measure.tier != "wake",
            -_distance(each),
        ),
    )


def _distance(each: Line) -> float:
    """A measure worse than its baseline has a value and a baseline, or it would read `none`."""
    value, baseline = each.reading.value or 0.0, each.reading.baseline or 0.0
    if baseline == 0:
        return abs(value)
    return abs(value - baseline) / abs(baseline)


def _amount(value: float | None, unit: str) -> str:
    return "none" if value is None else kpis.amount(value, unit)


def _note(reading: Reading) -> str:
    """The kind of error of a query that failed, never its message, which can carry the SQL's
    values, or else what the source's `note` says; a measure that `Lacks` its record says so in
    its row instead."""
    if reading.failed:
        return f"its query failed ({reading.note.split(':', 1)[0]})"
    return reading.note


def parts(measure: Measure, reading: Reading) -> list[str]:
    """Each part the reading is the worst of, with its value and its line: `prime 10 of 5 M
    units an hour`, or `prime 10 M units an hour, no line yet`."""
    return [
        f"{part.label} {kpis.amount(part.value, '')} {measure.each_unit}, no line yet"
        if part.line is None
        else f"{part.label} {kpis.amount(part.value, '')} of {kpis.amount(part.line, '')} "
        f"{measure.each_unit}"
        for part in reading.each
    ]


def sparkline(days: tuple[float | None, ...], state: State) -> str:
    """Six lines of SVG: the days that have a value, scaled from their least to their most, and a
    dot on the last."""
    width, height = 92, 22
    points = [
        (4 + i * (width - 8) / (len(days) - 1), value)
        for i, value in enumerate(days)
        if value is not None
    ]
    if not points:
        return "<span class=quiet>no value in 7 days</span>"
    least, most = min(v for _, v in points), max(v for _, v in points)
    span = (most - least) or 1
    placed = [(x, height - 3 - (v - least) / span * (height - 6)) for x, v in points]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in placed)
    x, y = placed[-1]
    shown = ", ".join(_short(v) for v in days)
    return (
        f"<svg class='sp s-{state}' viewBox='0 0 {width} {height}' role=img "
        f"aria-label='the last 7 days, oldest first: {shown}'><title>{shown}</title>"
        f"<polyline fill=none stroke=currentColor stroke-width=1.6 points='{path}'/>"
        f"<circle cx={x:.1f} cy={y:.1f} r=2.4 fill=currentColor /></svg>"
    )


def _short(value: float | None) -> str:
    """A day's value in three figures, or whole from 100 up: `0.301`, `21.9`, `1,234`."""
    if value is None:
        return "none"
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:.3g}"


def _tier(measure: Measure) -> str:
    said = "wakes the user" if measure.tier == "wake" else "shown here only"
    if measure.wired:
        said += f"; raised today as {measure.wired}"
    return said


def _row(each: Line) -> str:
    e = html.escape
    measure, reading = each.measure, each.reading
    state = reading.state
    if isinstance(measure.source, Lacks):
        now = f"<td class=quiet>no record yet: needs {e(measure.source.needs)}</td>"
        query = ""
    else:
        note = _note(reading)
        shown = _amount(reading.value, measure.unit)
        now = (
            f"<td><b>{e(shown)}</b> <span class=quiet>of {reading.n}, "
            f"{WINDOWS[measure.window]}</span>"
            + (f"<div class=quiet>{e(note)}</div>" if note else "")
            + "".join(f"<div>{e(said)}</div>" for said in parts(measure, reading))
            + "</td>"
        )
        query = f"<pre>{e(measure.source.query)}</pre>"
    days = sparkline(each.days, state) if each.days else ""
    baseline = (
        f"{e(_amount(reading.baseline, measure.unit))}"
        f"<div class=quiet>from {e(measure.baseline_of)}</div>"
    )
    return (
        f"<tr data-measure='{e(measure.name)}'>"
        f"<th scope=row>{e(measure.name)}<details><summary>what it counts</summary>"
        f"<p>{e(measure.says)}</p>{query}</details></th>"
        f"{now}<td class=days>{days}</td><td>{baseline}</td>"
        f"<td><span class='chip s-{state}'><span class=dot></span>{WORDS[state]}</span></td>"
        f"<td class=quiet>{e(_tier(measure))}</td></tr>"
    )


def _band(found: list[Line]) -> str:
    e = html.escape
    ranked = worst(found)
    seen = counts(found)
    if not ranked:
        return (
            f"<div class='band s-ok-band'>All {len(found) - seen['none']} measures with a reading "
            "are at or better than their baseline.</div>"
        )
    named = "; ".join(
        f"<span class=s-{each.reading.state}>{e(each.measure.name)}</span> "
        f"{e(_amount(each.reading.value, each.measure.unit))} "
        f"<span class=quiet>(baseline "
        f"{e(_amount(each.reading.baseline, each.measure.unit))})</span>"
        for each in ranked[:3]
    )
    level = "bad" if seen["bad"] else "watch"
    return (
        f"<div class='band s-{level}-band'><b>{len(ranked)} of {len(found)} worse than their "
        f"baseline</b>, {seen['bad']} of them past their line. Worst: {named}.</div>"
    )


_STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202b;--mut:#5c6b7a;--line:#dde3ea;--ok:#1f8a4c;
--watch:#b7791f;--bad:#c53030;--none:#7a8794;--acc:#2b6cb0;--chip:#eef2f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161c;--card:#1a212a;
--ink:#e6ebf0;--mut:#93a1b0;--line:#2b3542;--ok:#4cc38a;--watch:#e0a84a;--bad:#f07178;
--none:#7f8b98;--acc:#6aa9e9;--chip:#232c37}}
:root[data-theme="dark"]{--bg:#11161c;--card:#1a212a;--ink:#e6ebf0;--mut:#93a1b0;--line:#2b3542;
--ok:#4cc38a;--watch:#e0a84a;--bad:#f07178;--none:#7f8b98;--acc:#6aa9e9;--chip:#232c37}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:14px;margin:26px 0 6px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
p{margin:6px 0}.quiet{color:var(--mut);font-size:12.5px}
.band{padding:10px 14px;border-radius:8px;margin:14px 0;border-left:5px solid currentColor}
.s-bad-band{border-color:var(--bad);background:color-mix(in srgb,var(--bad) 14%,transparent)}
.s-watch-band{border-color:var(--watch);background:color-mix(in srgb,var(--watch) 14%,transparent)}
.s-ok-band{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 12%,transparent)}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{color:var(--mut);font-weight:600;font-size:12px}
tbody th{font-weight:600;width:26%}
.chip{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;
background:var(--chip);white-space:nowrap}
.s-ok{color:var(--ok)}.s-watch{color:var(--watch)}.s-bad{color:var(--bad)}.s-none{color:var(--none)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;
background:currentColor}
svg.sp{width:92px;height:22px;vertical-align:middle}
details summary{cursor:pointer;color:var(--acc);font-size:12px;font-weight:400}
details p{font-weight:400}
pre{white-space:pre-wrap;word-break:break-word;font-size:12px;background:var(--chip);
padding:8px;border-radius:6px;margin:4px 0;font-weight:400}
@media (max-width:640px){
thead{display:none}table,tbody,tr,th,td{display:block;width:auto}
tr{border-bottom:1px solid var(--line);padding:6px 0}th,td{border:0;padding:2px 10px}
tbody th{width:auto}
}
"""


def page(readings: list[Line], now: datetime) -> str:
    """The whole page: the band, then a table a group, a row a measure."""
    by_group = {
        group: [each for each in readings if each.measure.group == group] for group in GROUPS
    }
    head = (
        "<thead><tr><th>Measure</th><th>Now</th><th>Last 7 days</th><th>Baseline</th>"
        "<th>State</th><th>Raised as</th></tr></thead>"
    )
    tables = "".join(
        f"<h2>{group}</h2><div class=wrap><table>{head}<tbody>"
        f"{''.join(_row(each) for each in rows)}</tbody></table></div>"
        for group, rows in by_group.items()
        if rows
    )
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>Health scorecard</title><style>{_STYLE}</style></head><body><main>"
        "<h1>Health scorecard</h1>"
        f"<p class=quiet>Built {now:%Y-%m-%d %H:%M %Z} by a pass of jbus from the telemetry store "
        "alone. A measure is <b class=s-ok>ok</b> at or better than its baseline, "
        "<b class=s-watch>watch</b> worse than it, <b class=s-bad>bad</b> past the line its kind "
        "draws (any count above 0, a limit, or a margin worse than its own seven days before), "
        "and <b class=s-none>none</b> with no reading. Only a measure of today has a sparkline: "
        "each day's point is the same part of that day as today so far.</p>"
        f"{_band(readings)}{tables}</main></body></html>\n"
    )
