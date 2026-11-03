"""The KPIs that say whether jstack meets its vision, and the static page of them that `jbus kpis`
builds out of the telemetry store: each KPI against its target, this week and last.

`KPIS` is the registry, one `Kpi` each, in the order of the telemetry-plane scout's report
(`scouts/telemetry-plane.md` in the home, its section 2). A KPI is `Measured` by a weekly view of
the store (`jbus.telemetry.schema.VIEWS`), or `Lacks` the instrument it needs, which the page
says. The targets are the report's, which the user confirms or changes here.

A week starts on Sunday in the user's zone, as the views' `week` does. Each week of the two gets
its own `Reading`: its value, how many it is of, and its `Status`. This week is the one so far.

The page reads only the store: it calls no `gh` and no service. It names no project, no row,
no path and no thread, and the store holds no text of a message, so `jleak` finds nothing in it.
"""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

Status = Literal["met", "missed", "tracked", "no data", "not covered"]
"""A measured KPI's week: at its target or past it, `tracked` where it has no target,
`no data` where nothing in the week counts toward it, and `not covered` where the week begins
before the records the KPI needs do, so its value would not count what a later week's does."""


@dataclass(frozen=True)
class Measured:
    """A KPI one of the store's weekly views gives: `value` and `n`, how many the value is of, as
    SQL over one week's row of `view`, and `empty`, the value of a week the view has no row for:
    0 for a count, None where there is nothing to count. `since` names a view whose one row's
    `day` is the first day the KPI's `records` cover, where a week that begins before it would
    count something other than a later week does."""

    view: str
    value: str
    n: str
    empty: float | None = None
    since: str | None = None
    records: str = ""


@dataclass(frozen=True)
class Lacks:
    """A KPI the store has no instrument for yet, and what it needs."""

    needs: str


@dataclass(frozen=True)
class Kpi:
    name: str
    theme: str
    definition: str
    unit: str
    target: float | None
    better: Literal["lower", "higher"]
    source: Measured | Lacks


@dataclass(frozen=True)
class Reading:
    value: float | None
    n: int
    status: Status
    note: str = ""


NO_TEXT = "the store keeps no text of a message (2026-11-02)"

KPIS: tuple[Kpi, ...] = (
    Kpi(
        "PR open to merge, median",
        "speed",
        "minutes from a pull request's opening to its merge, of those jmerge merged",
        "min",
        10,
        "lower",
        Measured("weekly_pr_to_merge", "median", "n"),
    ),
    Kpi(
        "Lead time, go to merge, median (DORA)",
        "speed",
        "minutes from a row's go to its merge (S5)",
        "min",
        30,
        "lower",
        Measured("weekly_lead_time", "median", "n"),
    ),
    Kpi(
        "Change failure rate, push checks (DORA)",
        "main",
        "merged rows whose pull request opened a red spell of main's push checks (S6)",
        "%",
        2,
        "lower",
        Measured("weekly_change_failure", "100.0 * rate", "merged"),
    ),
    Kpi(
        "Time to restore main, median (DORA)",
        "main",
        "minutes from a push check's first failure on main to its next pass (S7)",
        "min",
        15,
        "lower",
        Measured("weekly_restore", "median", "spells"),
    ),
    Kpi(
        "Merges a week (DORA frequency)",
        "speed",
        "rows merged in the week",
        "",
        None,
        "higher",
        Measured("weekly_merges", "merged", "merged", empty=0),
    ),
    Kpi(
        "Your typed messages per merged row",
        "attention",
        "messages you typed, not resume clicks, over rows merged in the week",
        "",
        0.5,
        "lower",
        Measured("weekly_typed_per_row", "per_row", "merged"),
    ),
    Kpi(
        "'What needs me' asks",
        "attention",
        "times you asked what needs you",
        "",
        0,
        "lower",
        Lacks(
            "a label of what each message asks, recorded as it is written: the ask ledger "
            f"joins a message to its row, answer or reply, not to what it asked; {NO_TEXT}"
        ),
    ),
    Kpi(
        "Rows finished with no further word",
        "autonomy",
        "merged rows with no message you typed after their go naming them: cited by an act on "
        "the row, or typed in its crew's thread (S1)",
        "%",
        95,
        "higher",
        Measured("weekly_no_word", "share", "merged"),
    ),
    Kpi(
        "Gates closed by silence that were wrong (S8)",
        "attention",
        "closes by silence later corrected, over closes with a known outcome",
        "%",
        5,
        "lower",
        Lacks("a scout's labels each week (gate-labels)"),
    ),
    Kpi(
        "Doors opened without your own word",
        "safety",
        "door acts done by a home, a bot or jbus, not by you",
        "",
        0,
        "lower",
        Measured("weekly_doors", "not_yours", "done", empty=0),
    ),
    Kpi(
        "Spend per merged row (M units)",
        "cost",
        "jgauge spend units of a merged row's own threads, of every provider, over the "
        "week's merged rows with any call recorded",
        "M",
        None,
        "lower",
        Measured("weekly_row_spend", "per_row", "rows"),
    ),
    Kpi(
        "Coordination share of spend",
        "cost",
        "jbus sends and homes over all spend, of the runs jgauge spend counts",
        "%",
        20,
        "lower",
        Measured("weekly_spend", "coordination", "days"),
    ),
    Kpi(
        "Dollars per merged row",
        "cost",
        "billed dollars over rows merged",
        "$",
        None,
        "lower",
        Lacks("cost_usd from the agents' OpenTelemetry (design C) or a price table"),
    ),
    Kpi(
        "Crew first-round share",
        "quality",
        "merged pull requests with no red check and no wait on a crew's fix round, of those "
        "whose pull_request checks the CI ledger kept",
        "%",
        50,
        "higher",
        Measured(
            "weekly_first_round",
            "share",
            "n",
            since="fix_rounds_since",
            records="jmerge's waits labelled as a crew's fix round",
        ),
    ),
    Kpi(
        "Redo rate",
        "quality",
        "merged rows a later row fixes or reverts within 7 days",
        "%",
        5,
        "lower",
        Lacks("a record of the merged row a later row fixes or reverts: no record names it"),
    ),
    Kpi(
        "Capped minutes (every instance capped)",
        "reliability",
        "minutes a day with every agent instance capped",
        "min",
        0,
        "lower",
        Lacks("a record of capped spells: the limits files hold the current value only"),
    ),
    Kpi(
        "Capped-failure share of spend",
        "reliability",
        "spend of runs that failed on a usage limit or part way, over all spend, of the runs "
        "jgauge spend counts",
        "%",
        1,
        "lower",
        Measured("weekly_spend", "capped", "days"),
    ),
    Kpi(
        "Stall minutes per merged row",
        "speed",
        "minutes a running row was quiet or hung",
        "min",
        None,
        "lower",
        Lacks("a record of how long a row was quiet: hung.jsonl stopped on 2026-10-26"),
    ),
    Kpi(
        "Lost asks (S3)",
        "attention",
        "asks of yours with no row, answer or reply",
        "",
        0,
        "lower",
        Measured("weekly_lost_asks", "lost", "typed", empty=0),
    ),
    Kpi(
        "jbus pass, median seconds",
        "speed",
        "wall clock of one jbus pass",
        "s",
        30,
        "lower",
        Measured("weekly_pass_time", "median", "n"),
    ),
    Kpi(
        "Waiting for jmerge, PR p50 minutes",
        "speed",
        "minutes a green pull request waits for jmerge",
        "min",
        0.25,
        "lower",
        Lacks("jmerge's waits in seconds: merge.log stamps minutes, not when a blocker cleared"),
    ),
    Kpi(
        "Crew first load, KB (jstack's own)",
        "cost",
        "skill and playbook read before a crew's work",
        "KB",
        16,
        "lower",
        Lacks("the installed files' size as a record a week: it is measured by hand"),
    ),
    Kpi(
        "Drift: standing words broken (S4)",
        "attention",
        "probed standing instructions broken at the week's end",
        "",
        0,
        "lower",
        Lacks("the probes run each week: they are a fixed list run by hand"),
    ),
)


def week_of(day: date) -> date:
    """The Sunday the week of `day` starts on, as the views' `week`."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def read(store: sqlite3.Connection, kpi: Kpi, week: date) -> Reading | None:
    """A measured KPI's week, or None for one the store has no instrument for."""
    source = kpi.source
    if isinstance(source, Lacks):
        return None
    if source.since:
        found = store.execute(f"SELECT day FROM {source.since}").fetchone()
        start = found[0] if found else None
        if start is None:
            return Reading(None, 0, "not covered", f"{source.records} have no line yet")
        if week.isoformat() < start:
            note = f"{source.records} begin on {start}, after the week does"
            return Reading(None, 0, "not covered", note)
    row = store.execute(
        f"SELECT {source.value}, {source.n} FROM {source.view} WHERE week = ?",
        (week.isoformat(),),
    ).fetchone()
    value, n = (row[0], row[1] or 0) if row else (source.empty, 0)
    if value is None:
        return Reading(None, n, "no data")
    if kpi.target is None:
        return Reading(value, n, "tracked")
    met = value <= kpi.target if kpi.better == "lower" else value >= kpi.target
    return Reading(value, n, "met" if met else "missed")


def _number(value: float) -> str:
    return f"{round(value, 1):g}"


def amount(value: float, unit: str) -> str:
    """A value with its unit: `59 min`, `3.6%`, `$2`, `12`."""
    if unit == "$":
        return f"${_number(value)}"
    if unit in ("", "%"):
        return f"{_number(value)}{unit}"
    return f"{_number(value)} {unit}"


def target(kpi: Kpi) -> str:
    if kpi.target is None:
        return "none yet"
    return f"{'≤' if kpi.better == 'lower' else '≥'} {amount(kpi.target, kpi.unit)}"


@dataclass(frozen=True)
class Board:
    """Each KPI's two weeks, last and this, with when the store was last built."""

    this: date
    built: str | None
    rows: tuple[tuple[Kpi, Reading | None, Reading | None], ...]

    @property
    def last(self) -> date:
        return self.this - timedelta(days=7)

    def count(self, which: int, status: Status) -> int:
        return sum(1 for row in self.rows if row[which] and row[which].status == status)

    def judged(self, which: int) -> int:
        return self.count(which, "met") + self.count(which, "missed")

    @property
    def lacking(self) -> int:
        return sum(1 for kpi, *_ in self.rows if isinstance(kpi.source, Lacks))

    def line(self) -> str:
        return (
            f"last week ({self.last}) {self.count(1, 'met')} of {self.judged(1)} met, "
            f"this week ({self.this}) {self.count(2, 'met')} of {self.judged(2)} so far, "
            f"{self.lacking} of {len(self.rows)} with no instrument yet"
        )


def board(store: sqlite3.Connection, today: date) -> Board:
    this = week_of(today)
    found = store.execute("SELECT max(at) FROM builds").fetchone()
    return Board(
        this,
        found[0] if found else None,
        tuple(
            (kpi, read(store, kpi, this - timedelta(days=7)), read(store, kpi, this))
            for kpi in KPIS
        ),
    )


_STYLE = """
:root { color-scheme: light dark; --met: #1a7f37; --missed: #cf222e; --quiet: #6e7781; }
body { font: 14px/1.45 system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; }
h1 { font-size: 1.4rem; margin-bottom: .2rem; }
.lede { color: var(--quiet); margin-top: 0; }
.tiles { display: flex; gap: 1rem; margin: 1rem 0 1.5rem; flex-wrap: wrap; }
.tile { border: 1px solid #8884; border-radius: 8px; padding: .6rem 1rem; min-width: 10rem; }
.tile b { display: block; font-size: 1.6rem; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; vertical-align: top; padding: .45rem .6rem; }
tbody tr { border-bottom: 1px solid #8883; }
thead th { font-size: .8rem; text-transform: uppercase; color: var(--quiet); }
td.what, td.theme { color: var(--quiet); font-size: .85rem; }
td.week { white-space: nowrap; }
.n { color: var(--quiet); font-size: .8rem; }
.met { color: var(--met); font-weight: 600; }
.missed { color: var(--missed); font-weight: 600; }
.tracked, .nodata, .notcovered, .lacks { color: var(--quiet); }
td.lacks { font-size: .85rem; }
"""


def _cell(kpi: Kpi, reading: Reading) -> str:
    shown = "n/a" if reading.value is None else amount(reading.value, kpi.unit)
    kind = reading.status.replace(" ", "")
    note = f": {html.escape(reading.note)}" if reading.note else ""
    return (
        f"<td class=week><b>{html.escape(shown)}</b> <span class=n>n {reading.n}</span> "
        f"<span class={kind}>{reading.status}{note}</span></td>"
    )


def page(found: Board, now: datetime) -> str:
    """The page: a headline count for each week, then a row a KPI."""
    e = html.escape
    rows = []
    for kpi, last, this in found.rows:
        head = (
            f"<tr><th scope=row>{e(kpi.name)}</th><td class=what>{e(kpi.definition)}</td>"
            f"<td class=theme>{e(kpi.theme)}</td><td>{e(target(kpi))}</td>"
        )
        if isinstance(kpi.source, Lacks):
            weeks = f"<td class=lacks colspan=2>no instrument yet: needs {e(kpi.source.needs)}</td>"
        else:
            assert last is not None and this is not None
            weeks = _cell(kpi, last) + _cell(kpi, this)
        rows.append(f"{head}{weeks}</tr>")
    last_span = f"{found.last} to {found.last + timedelta(days=6)}"
    this_span = f"from {found.this}"
    built = (
        f"; the store was last built {e(found.built[:16].replace('T', ' '))} UTC"
        if found.built
        else ""
    )
    tiles = "".join(
        f"<div class=tile><b>{value}</b>{e(label)}</div>"
        for value, label in (
            (f"{found.count(1, 'met')} of {found.judged(1)}", "met last week"),
            (f"{found.count(2, 'met')} of {found.judged(2)}", "met this week so far"),
            (f"{found.lacking} of {len(found.rows)}", "with no instrument yet"),
        )
    )
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>Is the vision met this week?</title><style>{_STYLE}</style></head><body>"
        "<h1>Is the vision met this week?</h1>"
        f"<p class=lede>Each KPI against its target, last week ({last_span}) and this week so far "
        f"({this_span}). Built {now:%Y-%m-%d %H:%M %Z} by <code>jbus kpis</code> from the "
        f"telemetry store{built}.</p>"
        f"<div class=tiles>{tiles}</div>"
        "<table><thead><tr><th>KPI</th><th>what it counts</th><th>theme</th><th>target</th>"
        f"<th>last week, {last_span}</th><th>this week, {this_span}</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>\n"
    )
