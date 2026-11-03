"""The KPI alerts: each threshold of the KPIs, read each pass, raised once when it is crossed.

A threshold is a count against a limit, never a burn rate, since a day has too few events for
one. `THRESHOLDS` is the registry, and each reads its count for each owner it covers: a project,
or the machine (`alert.MACHINE`).

- `doors`: the one-way doors opened today without the user's word, an act that is `done` on a
  door by a party whose words jbus did not read in T3 Code itself (`party.opens`). It alerts on 1.
- `main-red`: the minutes main's push check was red today, a red spell still open counted up to
  now (`main_spells`). It alerts over 30.
- `capped`: the minutes today in which every instance `jgauge spend` counts was capped, from the
  usage-limit failures in T3 Code's store. It alerts over 30.
- `lost-asks`: the asks lost today, each a message the user typed that `ask_ledger` says is
  `unanswered`, counted on the day it was lost, `schema.WAIT` minutes after it was typed, so an
  ask typed before midnight and lost after it is the next day's. It alerts on 1.
- `pass-time`: the 90th percentile of the seconds of jbus's passes that started in the last hour
  (`passes`). It alerts over 60, and only once the store holds a pass an hour old, so a whole hour
  is read.

All but `capped` read the telemetry store (`jbus.telemetry`), which the chore before this one
brings up to date. A count that cannot be read, with no store or no T3 Code store, is no
count, and its alert stays as it was.

Before the store is built, the chore `the capped read` appends the pass's read of which instances
the ledger has capped to the record of capped spells (`jgauge.limits.note`), from which the store
gives the KPI page its capped minutes. The `capped` alert still reads T3 Code's store.

An alert is an alert of the one list (`jbus.alert`), so it reaches its owner's home as every
other alert does. A crossing opens it once, under a key of its threshold and owner, and of the
day for a daily count. While it is open, a pass that finds the count still crossed leaves it as
it was, whatever the count has become. A daily alert ends with its day, and the next day's
crossing is a new alert. An alert whose count is no longer crossed ends with a `recovered` line,
and the next crossing opens it again.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import jbus
from jbus import alert, boxes, telemetry, verbs
from jbus.telemetry import records, schema
from jgauge import limits, spend

Say = Callable[[str], None]
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Look:
    """What a pass's look reads: the store, read only, now, and the user's day around now."""

    config: jbus.Config
    store: sqlite3.Connection | None
    now: datetime

    @property
    def day(self) -> date:
        return self.config.user.local(self.now).date()

    def midnight(self, day: date) -> datetime:
        """The local midnight that begins `day`, in UTC."""
        return self.config.user.local(datetime.combine(day, time())).astimezone(UTC)

    @property
    def begins(self) -> datetime:
        return self.midnight(self.day)

    @property
    def ends(self) -> datetime:
        return self.midnight(self.day + timedelta(days=1))


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(records.STAMP)


def _at(stamp: str) -> datetime:
    return datetime.strptime(stamp, records.STAMP).replace(tzinfo=UTC)


def _minutes(spans: list[tuple[datetime, datetime]], begin: datetime, end: datetime) -> float:
    """The minutes of the spans inside [begin, end)."""
    inside = [(max(s, begin), min(e, end)) for s, e in spans]
    return sum((e - s).total_seconds() for s, e in inside if s < e) / 60


def _doors(look: Look) -> dict[str, float]:
    if look.store is None:
        return {}
    found = dict(
        look.store.execute(
            "SELECT project, count(*) FROM acts WHERE doors > 0 AND outcome = 'done' "
            "AND at >= ? AND at < ? AND NOT (party IN ('user', 'home') AND checked = 1) "
            "GROUP BY project",
            (_stamp(look.begins), _stamp(look.ends)),
        ).fetchall()
    )
    return {project.name: found.get(project.name, 0) for project in look.config.projects}


def _main_red(look: Look) -> dict[str, float]:
    if look.store is None:
        return {}
    spells: dict[str, list[tuple[datetime, datetime]]] = {}
    for project, failed, green in look.store.execute(
        "SELECT project, first_fail_at, green_at FROM main_spells WHERE first_fail_at < ? "
        "AND (green_at IS NULL OR green_at > ?)",
        (_stamp(look.now), _stamp(look.begins)),
    ):
        end = _at(green) if green else look.now
        spells.setdefault(project, []).append((_at(failed), end))
    return {
        project.name: _minutes(spells.get(project.name, []), look.begins, look.now)
        for project in look.config.projects
    }


def _capped(look: Look) -> dict[str, float]:
    try:
        found, instances = spend.caps(boxes.store(), look.now)
    except spend.Refused:
        return {}
    spans = spend.capped_spans(found, instances)
    return {alert.MACHINE: _minutes(spans, look.begins, look.now)}


def _lost_asks(look: Look) -> dict[str, float]:
    if look.store is None:
        return {}
    lost = f"julianday(at) + {schema.WAIT} / 1440.0"
    found = dict(
        look.store.execute(
            f"SELECT project, count(*) FROM ask_ledger WHERE joined = 'unanswered' "
            f"AND {lost} >= julianday(?) AND {lost} < julianday(?) GROUP BY project",
            (_stamp(look.begins), _stamp(look.ends)),
        ).fetchall()
    )
    return {project.name: found.get(project.name, 0) for project in look.config.projects}


def _pass_time(look: Look) -> dict[str, float]:
    if look.store is None:
        return {}
    hour = _stamp(look.now - HOUR)
    first = look.store.execute(
        "SELECT min(at) FROM passes WHERE project = ? AND seconds IS NOT NULL", (alert.MACHINE,)
    ).fetchone()[0]
    if first is None or first > hour:
        return {}
    seconds = sorted(
        value
        for (value,) in look.store.execute(
            "SELECT seconds FROM passes WHERE project = ? AND at >= ? AND at <= ? "
            "AND seconds IS NOT NULL",
            (alert.MACHINE, hour, _stamp(look.now)),
        )
    )
    if not seconds:
        return {}
    return {alert.MACHINE: seconds[min(len(seconds) - 1, int(0.9 * len(seconds)))]}


def _count(value: float, one: str, many: str) -> str:
    return f"{value:.0f} {one if round(value) == 1 else many}"


@dataclass(frozen=True)
class Threshold:
    """A KPI's threshold: it is crossed where its count is over `over`. `daily` is a count of the
    user's day. `says` is what the count is, for the alert and the recovered line."""

    name: str
    over: float
    daily: bool
    read: Callable[[Look], dict[str, float]]
    says: Callable[[float, date], str]
    limit: str

    def key(self, owner: str, day: date) -> str:
        whose = f" {owner}" if owner else ""
        return f"kpi {self.name}{whose}" + (f" {day.isoformat()}" if self.daily else "")


THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(
        "doors",
        0,
        True,
        _doors,
        lambda n, day: (
            f"{_count(n, 'one-way door', 'one-way doors')} opened on {day} without the user's word"
        ),
        "and the threshold alerts on 1",
    ),
    Threshold(
        "main-red",
        30,
        True,
        _main_red,
        lambda minutes, day: f"main red {minutes:.0f} min on {day}",
        "over the threshold of 30 min",
    ),
    Threshold(
        "capped",
        30,
        True,
        _capped,
        lambda minutes, day: f"every instance capped {minutes:.0f} min on {day}",
        "over the threshold of 30 min",
    ),
    Threshold(
        "lost-asks",
        0,
        True,
        _lost_asks,
        lambda n, day: (
            f"{_count(n, 'ask', 'asks')} lost on {day}, with no act citing it and no reply "
            f"within {schema.WAIT} min"
        ),
        "and the threshold alerts on 1",
    ),
    Threshold(
        "pass-time",
        60,
        False,
        _pass_time,
        lambda seconds, _: f"jbus's pass p90 {seconds:.0f} s over the last hour",
        "over the threshold of 60 s",
    ),
)


def look(config: jbus.Config, now: datetime, say: Say) -> None:
    """Read each threshold's count for each owner, and open or end its alert."""
    where = telemetry.path(config)
    store = None
    if where.is_file():
        store = sqlite3.connect(f"file:{where}?mode=ro", uri=True, timeout=telemetry.BUSY_MS / 1000)
    try:
        seen = Look(config, store, now)
        for threshold in THRESHOLDS:
            for owner, count in threshold.read(seen).items():
                _judge(config, threshold, owner, count, seen, say)
    finally:
        if store is not None:
            store.close()


def _judge(
    config: jbus.Config, threshold: Threshold, owner: str, count: float, seen: Look, say: Say
) -> None:
    key = threshold.key(owner, seen.day)
    what = f"kpi {threshold.name}{f' {owner}' if owner else ''}: {threshold.says(count, seen.day)}"
    held = alert.streak(config.state_dir, key)
    shown = (lambda line: say(f"{owner}: {line}")) if owner else say
    if count > threshold.over:
        if held is not None and held.alerted:
            return
        line = f"alert: {what}, {threshold.limit}"
        ends = seen.ends.isoformat() if threshold.daily else ""
        alert.raise_(config, key, line, owner=owner, now=seen.now, ends=ends)
        shown(line)
    elif held is not None:
        line = f"{alert.RECOVERED}: {what}"
        alert.end(config, key, line)
        shown(line)


CHORES = (
    verbs.Chore(33, "the capped read", lambda _config, _, now, _say: limits.note(now, "pass")),
    verbs.Chore(36, "the KPI thresholds", lambda config, _, now, say: look(config, now, say)),
)
