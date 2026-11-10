"""The measures of the scorecard: each a reading of the telemetry store against its baseline, which
`jbus scorecard` prints, one line a measure.

Each measure is a module of this package, `m<NN>_<slug>.py`, whose `MEASURE` is one `Measure`
and holds no function of its own, and `MEASURES` holds them in the order of the modules' names
(`jbus.telemetry.entries`). `NN` is the measure's place: the first 41 are the rows of the
scorecard scout's visual (`reports/po-scorecard.html` in the home, its array `M`), in its order.

A measure is a daily or hourly reading against a baseline, where a KPI (`jbus.telemetry.kpis`) is
a weekly value against a target for the vision. A measure reads `Sql`, one SELECT over the store
that gives `value` and `n`, how many the value is of, over its window's bounds, or `Lacks` the
record it needs. Its `kind` says where it is past its line: `Zero`, `Limit` or `Trend`. A reading
is `ok`, `watch` where it is worse than the baseline, `bad` where it is past the kind's line, or
`none` where it cannot be judged.

The scorecard reads only the store: it writes no page and raises no alert. A measure whose
`wired` names an alert is one an alert of `jbus.kpis` or `jbus.health`, or a `main-red-*` row,
already raises, so nothing built on the scorecard raises it twice.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal

import jsettings
from jbus.telemetry import entries, values

Group = Literal["flow", "cost", "quality", "attention", "machinery"]
Better = Literal["lower", "higher"]
Tier = Literal["page", "wake"]
"""`wake` is a measure whose crossing is to wake the user; `page` is shown, never raised."""
State = Literal["ok", "watch", "bad", "none"]
Window = Literal["hour", "day", "week", "now"]
"""The span a measure reads, each ending now: the last hour; the user's day so far, from their
midnight; the user's week so far, from the midnight that begins its Sunday, as the weekly views'
`week`; and now alone, for a reading of the store's present state, such as the queue."""

MEASURE_MODULE = r"m\d\d_[a-z0-9_]+"
"""The name of a measure's module: its place, two digits, and its slug."""

MACHINE = ""
"""The project of a row of the machine as a whole, as `jbus.telemetry.kpis.MACHINE`."""

PRIOR_DAYS = 7
"""How many days before a `Trend` reads its own windows over, for their mean."""

SPANS = (
    "with spans as (select coalesce(s.thread, c.provider || ':' || c.session) as thread,"
    " min(c.at) as first, max(c.at) as last"
    " from calls c left join sessions s on s.provider = c.provider and s.session = c.session"
    " where c.day >= date(:begins, '-1 day') and c.day <= date(:ends, '+1 day')"
    " and c.at >= :begins and c.at < :ends group by 1)"
)
"""A CTE of each live session in the window: a thread from its first model call to its last, of
any session of it, as the window holds them. A call whose session no record names is a thread of
its own. `day`, the call's local day, lets the read use `calls_day` before it bounds `at`."""

SESSION_HOURS = "(select sum(julianday(last) - julianday(first)) * 24 from spans)"
"""The hours the window's live sessions were live, summed, read after `SPANS`."""


@dataclass(frozen=True)
class Sql:
    """One SELECT over the store that gives one row of `value` and `n`, how many the value is of,
    and takes only the named parameters `:project`, `:begins` and `:ends`, the window's bounds as
    UTC stamps (`values.STAMP`), `begins` in it and `ends` not. A `machine` measure reads the
    machine's rows: its `:project` is `MACHINE`, so it reads the same on every project."""

    query: str
    machine: bool = False


@dataclass(frozen=True)
class Lacks:
    """A measure the store has no record for yet, and the record it needs."""

    needs: str


Source = Sql | Lacks


@dataclass(frozen=True)
class Zero:
    """Past at any value above 0: a count that should never happen."""


@dataclass(frozen=True)
class Limit:
    """Past where the value is beyond `at` in the worse direction; read only with `n` at least
    `floor`, so a share of three runs is no reading."""

    at: float
    floor: int = 1


@dataclass(frozen=True)
class Trend:
    """Past where the value is worse than the mean of its own seven days before, each the same
    window that many days earlier, by more than `by` percent."""

    by: float


Kind = Zero | Limit | Trend


@dataclass(frozen=True)
class Measure:
    """`says` what it counts, `unit` its value's, `baseline` the value it is judged against and
    `baseline_of` where that is from. `wired` names the alert that already covers it, or is
    empty; `audit` holds the ranks of the counters of the audit (`reports/po-audit.html` in the
    home) it carries."""

    name: str
    group: Group
    says: str
    unit: str
    better: Better
    source: Source
    window: Window
    baseline: float | None
    baseline_of: str
    kind: Kind
    tier: Tier
    wired: str = ""
    audit: tuple[int, ...] = ()


@dataclass(frozen=True)
class Reading:
    value: float | None
    n: int
    baseline: float | None
    state: State
    note: str = ""


def bounds(
    window: Window, now: datetime, user: jsettings.Settings, back: int = 0
) -> tuple[str, str]:
    """The UTC stamps that begin and end `window` at `now`, or at the same time of the user's day
    `back` days before, so a day so far is compared with the same part of each earlier day."""
    local = user.local(now) - timedelta(days=back)
    ends = local.astimezone(UTC)
    match window:
        case "hour":
            begins = ends - timedelta(hours=1)
        case "day":
            begins = _midnight(user, local)
        case "week":
            begins = _midnight(user, local - timedelta(days=(local.weekday() + 1) % 7))
        case "now":
            begins = ends
    return _stamp(begins), _stamp(ends)


def _midnight(user: jsettings.Settings, local: datetime) -> datetime:
    return user.local(datetime.combine(local.date(), time())).astimezone(UTC)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(values.STAMP)


def read(
    store: sqlite3.Connection,
    measure: Measure,
    project: str,
    now: datetime,
    user: jsettings.Settings,
) -> Reading:
    """The measure's reading at `now` for `project`. A query that fails reads `none`, with its
    error as the note."""
    match measure.source:
        case Lacks(needs):
            return Reading(None, 0, measure.baseline, "none", f"needs {needs}")
        case Sql(query, machine):
            owner = MACHINE if machine else project
    try:
        value, n = _value(store, query, owner, *bounds(measure.window, now, user))
        prior: list[float] = []
        if isinstance(measure.kind, Trend) and value is not None:
            for back in range(1, PRIOR_DAYS + 1):
                before, _ = _value(store, query, owner, *bounds(measure.window, now, user, back))
                if before is not None:
                    prior.append(before)
    except sqlite3.Error as error:
        return Reading(None, 0, measure.baseline, "none", f"{type(error).__name__}: {error}")
    mean = sum(prior) / len(prior) if prior else None
    return Reading(value, n, measure.baseline, _state(measure, value, n, mean))


def _value(
    store: sqlite3.Connection, query: str, project: str, begins: str, ends: str
) -> tuple[float | None, int]:
    row = store.execute(query, {"project": project, "begins": begins, "ends": ends}).fetchone()
    if row is None:
        return None, 0
    value, n = row
    return (None if value is None else float(value)), int(n or 0)


def _state(measure: Measure, value: float | None, n: int, mean: float | None) -> State:
    """Where a value of `n` stands: past the kind's line, worse than the baseline, or neither."""
    if value is None or measure.baseline is None:
        return "none"
    match measure.kind:
        case Zero():
            past = value > 0
        case Limit(at, floor):
            if n < floor:
                return "none"
            past = _worse(measure.better, value, at)
        case Trend(by):
            step = by / 100 if measure.better == "lower" else -by / 100
            past = (
                mean is not None and mean != 0 and _worse(measure.better, value, mean * (1 + step))
            )
    if past:
        return "bad"
    return "watch" if _worse(measure.better, value, measure.baseline) else "ok"


def _worse(better: Better, value: float, than: float) -> bool:
    return value > than if better == "lower" else value < than


MEASURES: tuple[Measure, ...] = tuple(
    module.MEASURE for module in entries.modules(__name__, __path__, MEASURE_MODULE)
)
"""Each module's `MEASURE`, in the order of the modules' names."""
