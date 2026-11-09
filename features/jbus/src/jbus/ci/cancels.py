"""Which pull request check runs a newer push cancelled, though GitHub calls them failed.

check.yml's roll-up `check` fails at `every part passed` when a part was cancelled, since a skipped
required check would count as passed. When a newer push cancels a run's parts, the roll-up is then
the only job of the attempt that failed, and nothing in it was red. `jbus.ci.numbers` reads such a
roll-up as `cancelled`, and so does the store's `REPLACED` (`jbus.telemetry.schema`).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def replaced(jobs: list[dict[str, Any]]) -> set[int]:
    """Return the roll-up `check` jobs whose attempt a newer push cancelled, by their `job`."""
    attempts: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        if job["event"] == "pull_request":
            attempts[(job["run"], job["attempt"])].append(job)
    return {
        j["job"]
        for run in attempts.values()
        if any(one["conclusion"] == "cancelled" for one in run)
        and all(one["name"] == "check" for one in run if one["conclusion"] == "failure")
        for j in run
        if j["name"] == "check" and j["conclusion"] == "failure"
    }
