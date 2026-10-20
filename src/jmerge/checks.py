"""A pull request's checks in one word: the one reading of a rollup's check states.

`jmerge --checks` prints it for the crew and pr-review skills, and jbus reads its pull
requests with it. Each check counts by its latest run, as `ready.latest` reads the check
named `check`; what `jmerge` merges on is `ready.passed`, that one check alone.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from jmerge.ready import latest


def latest_of_each(rollup: list[dict]) -> list[dict]:
    """The latest run of every check of the rollup, as `latest` reads one."""
    names = dict.fromkeys(one.get("name") or one.get("context") for one in rollup)
    return [one for name in names for one in latest(rollup, name)]


def failed_jobs(rollup: list[dict]) -> list[tuple[str, str, str]]:
    """Each check that completed and did not pass, skip or end neutral, and has a job:
    its address, its repo and its job's number. `checks` asks GitHub whether the job ran a
    step."""
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
    """The address of each failed check whose job GitHub says ran no step: `job_of` gives a
    job as GitHub does, by repo and number, or {} where GitHub will not give it, which counts
    as a job that ran."""
    return frozenset(
        url for url, repo, job in failed_jobs(rollup) if job_of(repo, job).get("steps") == []
    )


_JOB_URL = re.compile(r"^https://[^/]*/([^/]*/[^/]*)/actions/runs/\d+/job/(\d+)$")


def check_state(one: dict, never: frozenset[str] = frozenset()) -> str:
    """One check's state: passed, pending, skipped, failed, or unstarted where its address is
    in `never`, the jobs GitHub says ran no step."""
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
    """A pull request's checks in one word, each check read by its latest run: none, failed,
    pending, unrun (no check passed: every one skipped or never started), unstarted (one
    never started beside checks that passed), or passed."""
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
