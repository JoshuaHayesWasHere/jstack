"""The span every stage of the lab reads, from the flags `lab.py` passes it: the fit's days, the
week it predicts or measures, and the time the week is read to.

    --store <copy> --fit 2026-10-19..2026-11-01 --week 2026-11-01 --end 2026-11-03T01:37:48Z

A day is a local date, as the store's `day` and `week` columns are, and a local midnight is the
machine's (the `TZ` of the process), as sqlite's `utc` modifier reads it. Weeks start on Sunday,
as the store's views do. `--end` is a UTC time: a row merged at or after it is not in the week.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

M = "((julianday({x}) - 2440587.5) * 1440.0)"
"""An ISO time as minutes since the epoch."""


def em(x: str) -> str:
    return M.format(x=x)


@dataclass(frozen=True)
class Span:
    fit_start: str
    cutoff: str
    week: str
    end: str

    @property
    def week_end(self) -> str:
        return (date.fromisoformat(self.week) + timedelta(days=7)).isoformat()

    @property
    def last_week(self) -> str:
        return (date.fromisoformat(self.week) - timedelta(days=7)).isoformat()

    def flags(self) -> list[str]:
        return ["--fit", f"{self.fit_start}..{self.cutoff}", "--week", self.week, "--end", self.end]


def parse_span(fit: str, week: str, end: str) -> Span:
    """The span the flags name, or a ValueError that says which flag is wrong."""
    start, sep, cutoff = fit.partition("..")
    if not sep:
        raise ValueError(f"--fit {fit}: give it as <first day>..<cutoff day>")
    try:
        a, b, w = date.fromisoformat(start), date.fromisoformat(cutoff), date.fromisoformat(week)
    except ValueError as e:
        raise ValueError(f"--fit and --week take days as YYYY-MM-DD: {e}") from None
    if not a < b:
        raise ValueError(f"--fit {fit}: the first day must come before the cutoff")
    if w.isoweekday() != 7:
        raise ValueError(f"--week {week}: a week starts on a Sunday, as the store's weeks do")
    if w < b:
        raise ValueError(
            f"--week {week} starts before the fit's cutoff {cutoff}: the week would leak into "
            "the fit"
        )
    return Span(start, cutoff, week, end)


def add_flags(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--store", type=Path, required=True, help="the copy of the store to read")
    ap.add_argument(
        "--fit", required=True, help="the fit's days, <first>..<cutoff>, the cutoff left out"
    )
    ap.add_argument("--week", required=True, help="the Sunday the predicted week starts on")
    ap.add_argument("--end", required=True, help="the UTC time the week is read to")
    ap.add_argument("--json", type=Path, help="write the stage's numbers here")


def from_args(ap: argparse.ArgumentParser, a: argparse.Namespace) -> Span:
    try:
        return parse_span(a.fit, a.week, a.end)
    except ValueError as e:
        ap.error(str(e))


def connect(store: Path) -> sqlite3.Connection:
    """The copy, opened read-only."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def local_midnight(db: sqlite3.Connection, day: str) -> float:
    return db.execute(f"SELECT {em("datetime(?, 'utc')")}", (day,)).fetchone()[0]


def minutes(db: sqlite3.Connection, at: str) -> float:
    return db.execute(f"SELECT {em('?')}", (at,)).fetchone()[0]


def bounds(db: sqlite3.Connection, span: Span) -> tuple[float, float]:
    """The week's first and last minute, the last cut at `--end`."""
    return local_midnight(db, span.week), min(
        local_midnight(db, span.week_end), minutes(db, span.end)
    )
