"""Throughput: how many pull requests merged on each of the last `DAYS` days, and their total.

A day is a day of the user's zone, and today is the last of them, up to now. The server asks
GitHub for the merges when the drawer opens (`github.GitHub.merged`), so the count is GitHub's,
and holds a merge made by hand as well as one `jmerge` made. The page asks for this panel at
`/panel/throughput.json`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jbus.ci.numbers import day_windows
from jbus.view.github import UNKNOWN
from jbus.view.state import Read

FIRST = False
DAYS = 7
NOT_ASKED = "no server asks GitHub here"
SHAPE = {
    "throughput": {
        "days": [{"day": None, "merged": None}],
        "total": None,
        "at": None,
        "read": None,
        "error": None,
    }
}


def tally(times: list[str], days: list[tuple[str, datetime, datetime]]) -> list[dict[str, Any]]:
    """The count of `times` that fall in each of `days`, each day as `day_windows` gives it."""
    moments = [datetime.fromisoformat(one) for one in times]
    return [
        {"day": name, "merged": sum(1 for one in moments if first <= one < last)}
        for name, first, last in days
    ]


def build(read: Read) -> dict[str, Any]:
    days = day_windows(read.now, DAYS, read.user.zone or read.user.local(read.now).tzinfo or UTC)
    if not read.where:
        asked: dict[str, Any] = {"merged": [], "at": None, "error": UNKNOWN}
    elif read.merged is None:
        asked = {"merged": [], "at": None, "error": NOT_ASKED}
    else:
        asked = read.merged(read.where, (days[0][1] - timedelta(days=1)).date())
    counted = tally([one["at"] for one in asked["merged"]], days)
    return {
        "throughput": {
            "days": counted,
            "total": sum(one["merged"] for one in counted),
            "at": asked.get("at"),
            "read": not asked.get("error"),
            "error": asked.get("error") or "",
        }
    }
