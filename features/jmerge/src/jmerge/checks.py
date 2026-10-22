from __future__ import annotations

import re
from collections.abc import Callable

from jmerge.ready import latest


def latest_of_each(rollup: list[dict]) -> list[dict]:
    names = dict.fromkeys(one.get("name") or one.get("context") for one in rollup)
    return [one for name in names for one in latest(rollup, name)]


def failed_jobs(rollup: list[dict]) -> list[tuple[str, str, str]]:
    found = []
    for one in rollup:
        if one.get("status") != "COMPLETED" or one.get("conclusion") in (
            "SUCCESS",
            "NEUTRAL",
            "SKIPPED",
        ):
            continue
        url = one.get("detailsUrl") or ""
        job = _JOB_URL.match(url)
        if job:
            found.append((url, *job.groups()))
    return found


def never_started(rollup: list[dict], job_of: Callable[[str, str], dict]) -> frozenset[str]:
    """The address of each failed check whose job, as GitHub says, ran no step. `job_of` gives a
    job as GitHub does, by repo and number, or {} where GitHub does not give it, and such a
    job counts as one that ran."""
    return frozenset(
        url for url, repo, job in failed_jobs(rollup) if job_of(repo, job).get("steps") == []
    )


_JOB_URL = re.compile(r"^https://[^/]*/([^/]*/[^/]*)/actions/runs/\d+/job/(\d+)$")


def check_state(one: dict, never: frozenset[str] = frozenset()) -> str:
    if one.get("state"):
        if one["state"] == "SUCCESS":
            return "passed"
        return "pending" if one["state"] in ("PENDING", "EXPECTED") else "failed"
    if one.get("status") != "COMPLETED":
        return "pending"
    if one.get("conclusion") in ("SUCCESS", "NEUTRAL"):
        return "passed"
    if one.get("conclusion") == "SKIPPED":
        return "skipped"
    return "unstarted" if (one.get("detailsUrl") or "") in never else "failed"


def checks(rollup: list[dict], never: frozenset[str] = frozenset()) -> str:
    each = [check_state(one, never) for one in latest_of_each(rollup)]
    if not each:
        return "none"
    for word in ("failed", "pending"):
        if word in each:
            return word
    if "passed" not in each:
        return "unrun"
    return "unstarted" if "unstarted" in each else "passed"


SAID = {
    "none": "wait: no check is reported yet",
    "failed": "failed: a check ran and failed",
    "pending": "wait: a check has not finished",
    "unrun": "unrun: no check ran at {head}",
    "unstarted": "failed: a check never started beside checks that ran",
    "passed": "passed: every check passed at {head}",
}
