"""How CI ran in a window, measured from the runs of `jbus.flow.records` and the jobs `jbus ci`
keeps: how long main was red and what that held up (`main_red`), the runs and their jobs' queue
and run time (`ci`), and the queue of the kept jobs by runner kind (`ledger_jobs`)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from jbus.flow.measure import OWN_CHECK, UNTIMED, Row, _hours, _quantile
from jbus.flow.records import Run, when


def main_red(found_runs: list[Run], found_rows: list[Row], merges: dict[str, dict]) -> dict:
    """Return, for each repo, how long main was red on its gate workflow (the workflow with the
    most runs on pushes to main), and what that held up: the rows whose wait was `main red`,
    their hours, and the pull requests that merged while it was red. Each other workflow of
    main's pushes is measured the same way under `by_workflow`, since one that stays red is a
    red nobody's rule reads. Each span names the run that turned it red and the run that ended it.

    A failed run that ended within `NO_JOB` of its start ran no job: GitHub started none, as on
    a failed payment or a spent limit. Such a run turns main neither red nor green. The time
    until the next run that did run a job is counted as `no_job_hours`, CI that did not run."""
    by_repo: defaultdict[str, list[Run]] = defaultdict(list)
    for run in found_runs:
        if run.event == "push" and run.branch == "main":
            by_repo[run.repo].append(run)
    said: dict[str, dict] = {}
    for repo, pushed in sorted(by_repo.items()):
        counted = Counter(one.workflow for one in pushed)
        gate = counted.most_common(1)[0][0]
        flows = {name: _red(pushed, name) for name in sorted(counted)}
        red, idle, ordered = flows[gate]
        spans = [(a, b) for a, b, *_ in red]
        merged = [at for at in merges.get(repo, {}).values() if any(a <= at <= b for a, b in spans)]
        said[repo] = {
            "gate": gate,
            "red_hours": _hours(spans),
            "red_spans": len(red),
            "merges_while_red": len(merged),
            "no_job_hours": _hours(idle),
            "no_job_runs": sum(1 for one in ordered if _no_job(one)),
            "spans": [
                {"start": a.isoformat(), "end": b.isoformat(), "red_run": r, "green_run": g}
                for a, b, r, g in red
            ],
            "by_workflow": {
                name: {
                    "red_hours": _hours([(a, b) for a, b, *_ in each[0]]),
                    "red_spans": len(each[0]),
                    "still_red": bool(each[0]) and each[0][-1][3] is None,
                    "no_job_hours": _hours(each[1]),
                    "no_job_runs": sum(1 for one in each[2] if _no_job(one)),
                    "runs": len(each[2]),
                }
                for name, each in flows.items()
            },
        }
    held = [one for one in found_rows if any(span.what == "main red" for span in one.spans)]
    return {
        "repos": said,
        "rows_held": len(held),
        "row_hours_held": round(
            sum(span.hours for one in held for span in one.spans if span.what == "main red"), 1
        ),
    }


RedSpan = tuple[datetime, datetime, int, int | None]


def _red(pushed: list[Run], workflow: str) -> tuple[list[RedSpan], list[tuple], list[Run]]:
    """Return when `workflow` was red on main, each span with the run that turned it red and
    the run that turned it green (None while it stays red), when CI ran no job, and the runs,
    read in the order the runs ended, since a run that ends last says what main is now."""
    ordered = sorted(
        (one for one in pushed if one.workflow == workflow and one.updated),
        key=lambda one: (one.updated, one.created),
    )
    red: list[RedSpan] = []
    idle: list[tuple[datetime, datetime]] = []
    start: Run | None = None
    down: datetime | None = None
    for run in ordered:
        if _no_job(run):
            down = down or run.updated
            continue
        if down is not None:
            idle.append((down, run.updated))  # type: ignore[arg-type]
            down = None
        if run.conclusion == "failure" and start is None:
            start = run
        elif run.conclusion == "success" and start is not None:
            red.append((start.updated, run.updated, start.id, run.id))  # type: ignore[arg-type]
            start = None
    if start is not None:
        red.append((start.updated, ordered[-1].updated, start.id, None))  # type: ignore[arg-type]
    last = ordered[-1].updated if ordered else None
    if down is not None and last is not None:
        idle.append((down, last))
    return red, idle, ordered


NO_JOB = timedelta(seconds=15)


def _no_job(run: Run) -> bool:
    began = run.started or run.created
    return run.conclusion == "failure" and run.updated is not None and run.updated - began < NO_JOB


def ci(found_runs: list[Run]) -> dict:
    """Return, for each repo, its runs, their conclusions, reruns, and the queue and run time
    of their jobs, on GitHub's runners and self-hosted ones, and the time of a pull request's
    finished `check` from its start to its last update. A run's `run_started_at` is its creation,
    not a runner's start, so a job's queue is known only with `--jobs`, or from `ledger_jobs`."""
    said = {}
    by: defaultdict[str, list[Run]] = defaultdict(list)
    for run in found_runs:
        by[run.repo].append(run)
    for repo, each in sorted(by.items()):
        ends = Counter(one.conclusion for one in each)
        queued = [q for one in each for q in one.queued]
        hosted = [q for one in each for q, h in zip(one.queued, one.hosted, strict=True) if h]
        ran = [r for one in each for r in one.ran]
        checked = [
            (one.updated - one.started).total_seconds()
            for one in each
            if one.workflow == OWN_CHECK
            and one.event == "pull_request"
            and one.started
            and one.updated
            and one.conclusion not in UNTIMED
        ]
        said[repo] = {
            "runs": len(each),
            "failure": ends.get("failure", 0),
            "cancelled": ends.get("cancelled", 0),
            "reruns": sum(1 for one in each if one.attempt > 1),
            "jobs": len(queued),
            "queue_hours": round(sum(queued) / 3600, 1),
            "queue_median_s": _quantile(queued, 0.5),
            "queue_p90_s": _quantile(queued, 0.9),
            "queue_self_hosted_hours": round((sum(queued) - sum(hosted)) / 3600, 1),
            "run_hours": round(sum(ran) / 3600, 1),
            "run_median_s": _quantile(ran, 0.5),
            "pr_checks": len(checked),
            "pr_check_median_s": _quantile(checked, 0.5),
            "pr_check_p90_s": _quantile(checked, 0.9),
        }
    return said


def ledger_jobs(jobs: dict[str, list[dict]], since: datetime, until: datetime) -> dict:
    """Return how long the jobs `jbus ci` kept in each project's `ci.jsonl` waited for a runner,
    by the runner's kind: a queue time that costs no call to GitHub."""
    said: dict[str, dict] = {}
    for name, kept in sorted(jobs.items()):
        inside = [
            one
            for one in kept
            if (made := when(one.get("created") or "")) is not None and since <= made <= until
        ]
        if not inside:
            continue
        found: dict[str, Any] = {"jobs": len(inside)}
        for kind in sorted({str(one.get("kind") or "?") for one in inside}):
            mine = [one for one in inside if str(one.get("kind") or "?") == kind]
            waited = [
                (began - made).total_seconds()
                for one in mine
                if (made := when(one.get("created") or ""))
                and (began := when(one.get("started") or ""))
            ]
            found[kind] = {
                "jobs": len(mine),
                "queue_hours": round(sum(waited) / 3600, 1),
                "queue_median_s": _quantile(waited, 0.5),
                "queue_p90_s": _quantile(waited, 0.9),
                "cancelled_waiting": sum(
                    1
                    for one in mine
                    if one.get("conclusion") == "cancelled" and not one.get("started")
                ),
            }
        made_at = [when(one["created"]) for one in inside]
        found["from"] = min(made_at).isoformat()  # type: ignore[type-var,union-attr]
        found["to"] = max(made_at).isoformat()  # type: ignore[type-var,union-attr]
        said[name] = found
    return said
