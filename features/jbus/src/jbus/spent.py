"""Each project's model spend, one line a day, kept from T3 Code's store (`jgauge.spend`).

`jgauge spend` reads T3 Code's store and prints, and keeps nothing. This chore keeps what it
counts, as two append-only logs in each project's state, read by the telemetry store:

- `spend.jsonl`: one line for each local day, in the user's zone: its units, runs and tokens,
  and its units by kind (`jgauge.spend.COLUMNS`). A day with no run has a line of zeros.
- `spend-rows.jsonl`: one line for each role and row of the day, by the title jbus gave the
  thread (`crew: <slug>`, `review: <slug>`, `home: ...`, `scout: <slug>`). A thread jbus did not
  name is `other`, with no slug, since its title is the user's.

A run counts whole on the day it started, as `jgauge spend` counts it. A day is kept once it
ended `SETTLE` ago, so the runs that started near its end have ended too, and never again. The
first time, the chore keeps the last `BACKFILL` days. It reads the store once a pass, for every
project, and only on a pass with a day to keep. A line names the project's runs by T3 Code's
project id. With no store on the machine, or one that cannot be read, it keeps nothing, and a
project whose state cannot be read is passed over, so it stops no other project's.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path

import jbus
from jbus import history, verbs
from jgauge import spend

FILE = "spend.jsonl"
ROWS = "spend-rows.jsonl"
BACKFILL = 30
SETTLE = timedelta(hours=6)


def _start(config: jbus.Config, day: date) -> datetime:
    """The first moment of a local day in the user's zone."""
    zone = config.user.zone
    moment = datetime.combine(day, time())
    return moment.replace(tzinfo=zone) if zone else moment.astimezone()


def _last(state: Path) -> date | None:
    """The last day `spend.jsonl` holds."""
    days = history.held(state / FILE, lambda one: one.get("day"), history.TAIL)
    found = [date.fromisoformat(day) for day in days if isinstance(day, str)]
    return max(found, default=None)


def due(config: jbus.Config, state: Path, now: datetime) -> list[date]:
    """The days to keep for a project: after the last it holds, at most `BACKFILL` back, up to
    the last that ended `SETTLE` ago."""
    newest = config.user.local(now - SETTLE).date() - timedelta(days=1)
    oldest = config.user.local(now).date() - timedelta(days=BACKFILL)
    last = _last(state)
    first = max(oldest, last + timedelta(days=1)) if last else oldest
    return [first + timedelta(days=n) for n in range((newest - first).days + 1)]


def keep(config: jbus.Config, now: datetime, store: Path = spend.STORE) -> int:
    """Keep each project's days that are due, and return how many lines of `spend.jsonl` it
    added."""
    owed = {}
    for project in config.projects:
        try:
            owed[project] = due(config, config.state(project), now)
        except OSError:
            continue
    days = sorted({day for found in owed.values() for day in found})
    if not days:
        return 0
    try:
        runs, _, _ = spend.read(
            store, _start(config, days[0]), _start(config, days[-1] + timedelta(days=1)), None
        )
    except spend.Refused:
        return 0
    added = 0
    for project, found in owed.items():
        try:
            added += _write(config, project, found, runs, now)
        except OSError:
            continue
    return added


def _write(config: jbus.Config, project: jbus.Project, found, runs, now: datetime) -> int:
    """Keep the project's days, and return how many it kept."""
    state, added = config.state(project), 0
    mine = [run for run in runs if run.project_id == project.project_id]
    for day in found:
        begin, end = _start(config, day), _start(config, day + timedelta(days=1))
        total, rows = spend.day_lines([r for r in mine if begin <= r.start < end], str(day))
        at = {"at": now.isoformat()}
        history.add(
            state / ROWS,
            [one | at for one in rows],
            lambda one: (one.get("day"), one.get("role"), one.get("slug")),
            history.TAIL,
        )
        history.add(state / FILE, [total | at], lambda one: one.get("day"), history.TAIL)
        added += 1
    return added


def _chore(config: jbus.Config, _, now: datetime, say: Callable[[str], None]) -> None:
    keep(config, now)


CHORES = (verbs.Chore(32, "each project's spend of the day", _chore),)
