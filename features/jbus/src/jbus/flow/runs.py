"""What a repo's Actions runs say of a window: queue, run time, cancels, reruns, a red main.

`fetch` asks for the runs created on each day of the window, one day a call, since GitHub
answers at most 1,000 runs for one query. A run's queue time is from its creation to the start
of its last attempt, and its run time from that start to its last update. A job's wait for a
runner is inside its run's time: `jbus ci`'s ledger has it, where it kept the job. A run with
`run_attempt` over 1 was rerun, and each attempt past the first is a rerun.

`red` reads main's push runs in the order they ended, one workflow at a time. A workflow goes
red when a run of it ends failed, and green when a run of it ends passed. A cancelled or
skipped run changes nothing. Main is red while any workflow is. Only the last attempt of a run
is in the list, so a failure that a rerun turned green is not seen.

Every call is a read through `gh api`. `Ask` is the interface: a test passes a function that
replies from a recording.
"""

from __future__ import annotations

import json
import statistics
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

Ask = Callable[[str], Any]
FAILED = frozenset({"failure", "timed_out", "startup_failure"})
PASSED = frozenset({"success"})


class Unavailable(Exception):
    """GitHub did not answer."""


def gh(path: str) -> Any:
    """Return GitHub's answer to a path, every page of it as a list where it has pages."""
    paged = "?" in path and "actions/runs" in path
    command = ["gh", "api", *(["--paginate", "--slurp"] if paged else []), path]
    try:
        asked = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise Unavailable(str(error)[:200]) from error
    if asked.returncode:
        raise Unavailable(" ".join(asked.stderr.split())[:200] or f"gh exit {asked.returncode}")
    return json.loads(asked.stdout)


def fetch(ask: Ask, repo: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Return every run created in the window, each once."""
    found: dict[int, dict[str, Any]] = {}
    day = since.date()
    while day <= until.date():
        pages = ask(f"repos/{repo}/actions/runs?created={day.isoformat()}&per_page=100")
        for page in pages if isinstance(pages, list) else [pages]:
            for run in page.get("workflow_runs") or []:
                created = when(run.get("created_at"))
                if created is not None and since <= created <= until:
                    found[run["id"]] = run
        day += timedelta(days=1)
    return sorted(found.values(), key=lambda run: run.get("created_at") or "")


def when(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")) if text else None
    except ValueError:
        return None


def minutes(start: str | None, end: str | None) -> float | None:
    begun, ended = when(start), when(end)
    if begun is None or ended is None or ended < begun:
        return None
    return (ended - begun).total_seconds() / 60


@dataclass
class Runs:
    """The numbers of one repo's runs in a window. Times are in minutes."""

    repo: str
    runs: int = 0
    failed: int = 0
    cancelled: int = 0
    rerun: int = 0
    attempts: int = 0
    queued: list[float] = field(default_factory=list)
    ran: list[float] = field(default_factory=list)
    red: list[tuple[datetime, datetime, str]] = field(default_factory=list)
    ran_red: int = 0


def red(
    runs: list[dict[str, Any]], branch: str, until: datetime
) -> list[tuple[datetime, datetime, str]]:
    """Return each stretch a workflow of `branch` was red, as `(start, end, workflow)`."""
    pushed = [
        run
        for run in runs
        if run.get("head_branch") == branch
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and when(run.get("updated_at")) is not None
    ]
    since: dict[str, datetime] = {}
    found: list[tuple[datetime, datetime, str]] = []
    for run in sorted(pushed, key=lambda run: when(run["updated_at"])):
        name, ended = str(run.get("name") or "?"), when(run["updated_at"])
        if run.get("conclusion") in FAILED:
            since.setdefault(name, ended)
        elif run.get("conclusion") in PASSED and name in since:
            found.append((since.pop(name), ended, name))
    found.extend((start, until, name) for name, start in since.items())
    return sorted(found)


def count(repo: str, runs: list[dict[str, Any]], branch: str, until: datetime) -> Runs:
    """Return the numbers of the runs."""
    made = Runs(repo, runs=len(runs))
    for run in runs:
        made.failed += run.get("conclusion") in FAILED
        made.cancelled += run.get("conclusion") == "cancelled"
        attempt = int(run.get("run_attempt") or 1)
        made.rerun += attempt > 1
        made.attempts += attempt - 1
        waited = minutes(run.get("created_at"), run.get("run_started_at"))
        if waited is not None:
            made.queued.append(waited)
        if run.get("status") == "completed":
            took = minutes(run.get("run_started_at"), run.get("updated_at"))
            if took is not None:
                made.ran.append(took)
    made.red = red(runs, branch, until)
    for run in runs:
        ended = when(run.get("updated_at"))
        if (
            run.get("event") == "pull_request"
            and run.get("conclusion") in FAILED
            and ended is not None
            and any(start <= ended <= end for start, end, _ in made.red)
        ):
            made.ran_red += 1
    return made


def spread(values: list[float]) -> str:
    """Return the median, the 90th centile and the sum of minutes, as a short line."""
    if not values:
        return "no data"
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return (
        f"median {statistics.median(ordered):.1f} min, p90 {p90:.1f} min, "
        f"total {sum(ordered) / 60:.1f} h"
    )
