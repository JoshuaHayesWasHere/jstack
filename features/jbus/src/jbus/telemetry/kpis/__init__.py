"""The KPIs that say whether jstack meets its vision, and the static page of them that `jbus kpis`
builds out of the telemetry store: each KPI against its target, this week and last.

Each KPI is a module of this package, `k<NN>_<slug>.py`, whose `KPI` is one `Kpi`, and `KPIS`
holds them in the order of the modules' names (`jbus.telemetry.entries`). `NN` is the KPI's place
on the page: the first 23 are in the order of the telemetry-plane scout's report
(`scouts/telemetry-plane.md` in the home, its section 2), and a KPI added since takes a number
after them, or between two where it belongs there. Two KPIs of the same number are in the order
of their slugs. A KPI is `Measured` by a weekly view of the store (`jbus.telemetry.views`), or
`Lacks` the instrument it needs, which the page says. The targets are the report's, which the
user confirms or changes in the KPI's module.

A week starts on Sunday in the user's zone, as the views' `week` does. Each week of the two gets
its own `Reading`: its value, how many it is of, and its `Status`. This week is the one so far.

The page reads only the store: it calls no `gh` and no service. It names no row, no path and no
thread, and no project but those a KPI says it covers, the projects whose push checks the store
keeps. The store holds no text of a message, so `jleak` finds nothing in it.
"""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from jbus.telemetry import entries

Status = Literal["met", "missed", "tracked", "no data", "not covered"]
"""A measured KPI's week: at its target or past it, `tracked` where it has no target,
`no data` where nothing in the week counts toward it, and `not covered` where the week begins
before the records the KPI needs do, so its value would not count what a later week's does, or
where those records are kept a week at a time and the week has none."""


@dataclass(frozen=True)
class Covers:
    """The projects a KPI counts, `projects` a view of `project`, and the days of a week whose
    rows it lacks the records of, `gaps` a view of `day`, `week` and `rows`, how many: `kept`
    names those records."""

    projects: str
    gaps: str
    kept: str


KPI_MODULE = r"k\d\d_[a-z0-9_]+"
"""The name of a KPI's module: its place on the page, two digits, and its slug."""

ROWS = "jbus's row records"
"""The records a KPI over merged rows reads, whose first day `rows_since` gives."""


@dataclass(frozen=True)
class Aside:
    """What a week's reading names beside its value, each with how many: `view` a view of `week`,
    `name` and `count`, `says` what the names are, before them, and `counts` what one of a count
    is, such as `call`."""

    view: str
    says: str
    counts: str


@dataclass(frozen=True)
class Measured:
    """A KPI one of the store's weekly views gives: `value` and `n`, how many the value is of, as
    SQL over one week's row of `view`, and `empty`, the value of a week the view has no row for:
    0 for a count, None where there is nothing to count. `since` names a view whose one row's
    `day` is the first day the KPI's `records` cover, where a week that begins before it would
    count something other than a later week does. `covers` is the projects and days it counts,
    where it counts only some. `missing`, where it is set, says why a week the view has no row for
    has no value: the records the KPI needs are kept a week at a time, and none for that week.
    `detail` is SQL over the week's row of `view` that gives the note of a week with a value, and
    `aside` what the week's reading names beside its value."""

    view: str
    value: str
    n: str
    empty: float | None = None
    since: str | None = None
    records: str = ""
    partial: bool = False
    """Read the week the records begin in, from that day, where it would be `not covered`."""
    covers: Covers | None = None
    missing: str | None = None
    detail: str | None = None
    aside: Aside | None = None


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


def week_of(day: date) -> date:
    """The Sunday the week of `day` starts on, as the views' `week`."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def read(store: sqlite3.Connection, kpi: Kpi, week: date) -> Reading | None:
    """A measured KPI's week, or None for one the store has no instrument for."""
    source = kpi.source
    if isinstance(source, Lacks):
        return None
    begins = ""
    if source.since:
        found = store.execute(f"SELECT day FROM {source.since}").fetchone()
        start = found[0] if found else None
        if start is None:
            return Reading(None, 0, "not covered", f"{source.records} have no line yet")
        if week.isoformat() < start:
            ends = (week + timedelta(days=7)).isoformat()
            if not source.partial or ends <= start:
                note = f"{source.records} begin on {start}, after the week does"
                return Reading(None, 0, "not covered", note)
            begins = f"from {start}, the day {source.records} begin"
    detail = source.detail or "''"
    row = store.execute(
        f"SELECT {source.value}, {source.n}, {detail} FROM {source.view} WHERE week = ?",
        (week.isoformat(),),
    ).fetchone()
    if row is None and source.missing:
        return Reading(None, 0, "not covered", source.missing)
    value, n = (row[0], row[1] or 0) if row else (source.empty, 0)
    notes = (
        _covered(store, source.covers, week) if source.covers else (row[2] if row else "") or begins,
        _aside(store, source.aside, week) if source.aside else "",
    )
    note = "; ".join(one for one in notes if one)
    if value is None:
        return Reading(None, n, "no data", note)
    if kpi.target is None:
        return Reading(value, n, "tracked", note)
    met = value <= kpi.target if kpi.better == "lower" else value >= kpi.target
    return Reading(value, n, "met" if met else "missed", note)


def _covered(store: sqlite3.Connection, covers: Covers, week: date) -> str:
    """Which projects the KPI counts, and the days of the week with rows it lacks the records of."""
    projects = [
        one for (one,) in store.execute(f"SELECT project FROM {covers.projects} ORDER BY 1")
    ]
    if not projects:
        return f"covers no project, since the store keeps no {covers.kept}"
    gaps = store.execute(
        f"SELECT day, sum(rows) FROM {covers.gaps} WHERE week = ? GROUP BY day ORDER BY day",
        (week.isoformat(),),
    ).fetchall()
    if not gaps:
        return f"covers {', '.join(projects)}"
    rows = sum(count for _, count in gaps)
    days = ", ".join(day for day, _ in gaps)
    lacks = f"no {covers.kept} kept for {rows} merged row{'s' * (rows != 1)}, on {days}"
    return f"covers {', '.join(projects)}; {lacks}"


def _aside(store: sqlite3.Connection, aside: Aside, week: date) -> str:
    """The names the week's reading gives beside its value, each with its count, or nothing."""
    named = store.execute(
        f"SELECT name, count FROM {aside.view} WHERE week = ? ORDER BY name",
        (week.isoformat(),),
    ).fetchall()
    if not named:
        return ""
    each = ", ".join(
        f"{name} ({count} {aside.counts}{'s' * (count != 1)})" for name, count in named
    )
    return f"{aside.says} {each}"


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


KPIS: tuple[Kpi, ...] = tuple(
    module.KPI for module in entries.modules(__name__, __path__, KPI_MODULE)
)
"""Each module's `KPI`, in the order of the modules' names."""
