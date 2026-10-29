"""This module runs a pull request's cancelled check again, once, and tells the home when that is
not enough.

GitHub ends a job `cancelled` when someone stops it, when a newer run of its concurrency group
displaces it, and when it runs past its `timeout-minutes` (`timed_out` too, in some answers).
`jmerge` then waits on the pull request, and no push or review moves it. So on each pass `rerun`
reads the required checks (`jmerge`'s `required-checks`) of each open row's pull request at its
head. A check whose latest run ran and ended cancelled or timed out is this module's, and not the
crew's (`stopped`): `rebase.ran_and_failed` leaves it out, so the crew is not told it failed. So is
a required check that failed because a job of its own workflow run was cancelled, and none failed:
the check workflow's `check` job waits on its four parts, and fails when one of them ran past its
`timeout-minutes`. The job that was cancelled is the one whose attempt, minutes and log count.

At its run's first attempt, `rerun` runs the workflow run again, `gh run rerun <run> --failed`,
once for the run, and journals one `cancelled` line that names the pull request and the run. At a
later attempt the check was cancelled twice, and a third run is not jbus's to start: `rerun` logs
one quiet stall, once for the head, with how long each attempt ran and the cause where the job's
log names one, and the one list takes it to the brief's home (`jbus.wakes`). A rerun that GitHub
refuses is logged the same way, and never tried again. The stall's line is the row's `why`
(`why`) while the check stays stopped at that head. Until then,
a row whose every failed check is of a run this module runs again is its own (`owns`), and no
blocker the home's `jbus clear` asks a fix for.

Only the head's own runs count. A check run whose job GitHub says ran on another commit belongs to
a head that a newer push displaced, and `rerun` neither runs it again nor tells anyone of it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from jbus import read_json, verbs, write_json
from jbus.passes import Pass
from jbus.watch import NEVER, World, job, job_log
from jmerge import ready
from jmerge.checks import check_state, latest_of_each

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"cancelled": "quiet"}
STALL = "stall"
STOPPED = ("CANCELLED", "TIMED_OUT")
FILE = "cancelled.json"
_JOB = re.compile(r"^/([^/]+/[^/]+)/actions/runs/(\d+)/job/(\d+)$")
_TIMEOUT = re.compile(r"exceeded the maximum execution time of (\d+) minutes")


def required(run: Pass) -> tuple[str, ...]:
    """Return the checks `jmerge` requires, from the home's `required-checks`."""
    try:
        text = (run.home / "required-checks").read_text(errors="replace")
    except OSError:
        text = ""
    return ready.required_of(text)


def stopped(
    check: dict, latest: list[dict], never: frozenset[str], names: tuple[str, ...]
) -> dict | None:
    """Return the job that stopped a required check of the rollup, or nothing. `latest` is the
    latest run of each check at the head. The job is the check's own where it ran and ended
    cancelled or timed out. Where the check failed, it is a job of the same workflow run that
    ended so, as long as no job of that run failed. A job that ran no step is `unrun`'s, not this
    module's."""
    url = check.get("detailsUrl") or ""
    if (
        (check.get("name") or check.get("context")) not in names
        or check.get("status") != "COMPLETED"
        or url in never
    ):
        return None
    if check.get("conclusion") in STOPPED:
        return check
    if check.get("conclusion") != "FAILURE" or not (run := run_of(url)):
        return None
    peers = [one for one in latest if one is not check and run_of(one.get("detailsUrl")) == run]
    if any(one.get("conclusion") == "FAILURE" for one in peers):
        return None
    return next((one for one in peers if one.get("conclusion") in STOPPED), None)


def run_of(url: str | None) -> str:
    """Return the workflow run of a check's job, from its address, or nothing."""
    found = _JOB.match(urlsplit(url or "").path)
    return found[2] if found else ""


def runs(latest: list[dict], never: frozenset[str], names: tuple[str, ...]) -> set[str]:
    """Return the workflow runs at the head that this module runs again or tells of: every job of
    such a run is its, and not a failed check to tell the crew of."""
    found = {run_of(one.get("detailsUrl")) for one in latest if stopped(one, latest, never, names)}
    return found - {""}


def why(run: Pass, slug: str) -> str:
    """Return the line the home got of the slug's cancelled check at its head, or nothing."""
    return str((read_json(run.state / FILE, {}).get(slug) or {}).get("why", ""))


def owns(run: Pass, slug: str) -> bool:
    """Return whether the slug's failed checks are all this module's, run again or to be, and its
    home has not been told of them."""
    kept = read_json(run.state / FILE, {}).get(slug)
    return kept is not None and not kept.get("why")


def rerun(run: Pass, world: World, slugs: set[str]) -> None:
    """Run each cancelled required check of an open row's pull request again once, at its first
    attempt, and log a stall of one cancelled again or that GitHub would not run again."""
    was: dict[str, dict[str, str]] = read_json(run.state / FILE, {})
    kept: dict[str, dict[str, str]] = {}
    names = required(run)
    for slug, pull in world.open.items():
        head = pull.get("headRefOid", "")
        if slug not in slugs or not head:
            continue
        never = frozenset(pull.get(NEVER) or ())
        latest = latest_of_each(pull.get("statusCheckRollup") or [])
        mine = False
        for check in latest:
            if cause := stopped(check, latest, never, names):
                said = _one(run, slug, pull, check, cause)
                mine = mine or said is not None
                if said:
                    kept[slug] = {"head": head, "why": said}
        theirs = runs(latest, never, names)
        failed = [one for one in latest if check_state(one, never) == "failed"]
        if (
            mine
            and slug not in kept
            and all(run_of(one.get("detailsUrl")) in theirs for one in failed)
        ):
            kept[slug] = {"head": head, "why": ""}
    if kept != was:
        write_json(run.state / FILE, kept)


def _one(run: Pass, slug: str, pull: dict, check: dict, stop: dict) -> str | None:
    """Act on one cancelled check, which the job `stop` stopped, and return the line of its stall,
    or nothing while it is run again. Return None for a check this module leaves alone."""
    found = _JOB.match(urlsplit(stop.get("detailsUrl") or "").path)
    if not found:
        return None
    repo, number, at = found.groups()
    head, pr = pull["headRefOid"], pull["number"]
    given = job(run, repo, at)
    if given.get("head_sha", head) != head:
        return None
    attempt = int(given.get("run_attempt") or 1)
    name = check.get("name") or check.get("context") or "check"
    its = "its check" if name == "check" else f"its check {name}"
    kept = read_json(run.state / FILE, {}).get(slug) or {}
    told = kept["why"] if kept.get("head") == head else ""
    if attempt > 1:
        if told and _told(slug, head) in run.box.sent():
            return told
        part = stop.get("name") or stop.get("context") or name
        minutes = [_minutes(_before(run, repo, number, attempt, part)), _minutes(given)]
        cause = _cause(run, repo, at, stop)
        when = _at(minutes)
        line = f"#{pr}: {its} was cancelled twice{',' + when if when else ''}"
        line += f": {cause}" if cause else ""
        return _tell(run, slug, head, line)
    key = f"rerun {number}"
    if f"cancelled|{slug}|{key}" in run.box.sent():
        return _tell(run, slug, head, told) if told else ""
    asked = run.run("gh", "run", "rerun", number, "--failed")
    if asked.returncode == 0:
        line = f"cancelled {slug}: ran #{pr}'s check again, run {number} at {head[:12]}"
        run.find(slug, "cancelled", line, key=key)
        run.say(line)
        return ""
    line = f"cancelled {slug}: GitHub did not run #{pr}'s check again, run {number} at {head[:12]}"
    run.find(slug, "cancelled", line, asked.stderr, key=key)
    refusal = (asked.stderr.strip().splitlines() or ["no reason given"])[0]
    line = f"#{pr}: {its} was cancelled{_at([_minutes(given)])}, and GitHub did not run it again"
    return _tell(run, slug, head, f"{line}: {refusal}")


def _told(slug: str, head: str) -> str:
    return f"{STALL}|{slug}|{FILE} {head[:12]}"


def _tell(run: Pass, slug: str, head: str, line: str) -> str:
    """Log the slug's cancelled check as one quiet stall, once for the head: the one list takes it
    to the brief's home (`jbus.wakes`), and with no home the log is the one record."""
    run.find(slug, STALL, f"{STALL} {slug}: {line}", key=f"{FILE} {head[:12]}")
    run.say(f"cancelled {slug}: {line}")
    return line


def _before(run: Pass, repo: str, number: str, attempt: int, name: str) -> dict:
    """Return the check's job in the run's attempt before `attempt`, or {} where GitHub gives
    none."""
    asked = run.run("gh", "api", f"repos/{repo}/actions/runs/{number}/attempts/{attempt - 1}/jobs")
    try:
        jobs = json.loads(asked.stdout).get("jobs") if asked.returncode == 0 else []
    except (ValueError, AttributeError):
        jobs = []
    return next((one for one in jobs or [] if one.get("name") == name), {})


def _minutes(given: dict[str, Any]) -> int | None:
    try:
        began = datetime.fromisoformat(given["started_at"])
        ended = datetime.fromisoformat(given["completed_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return round((ended - began).total_seconds() / 60)


def _at(minutes: list[int | None]) -> str:
    known = [str(one) for one in minutes if one is not None]
    if not known:
        return ""
    if len(set(known)) == 1:
        return f" at {known[0]} min" + (" each" if len(known) > 1 else "")
    return f" at {' and '.join(known)} min"


def _cause(run: Pass, repo: str, at: str, check: dict) -> str:
    """Return what the job's log says stopped it, or nothing where it names no cause."""
    log = job_log(run, repo, at)
    found = _TIMEOUT.search(log) if log is not None else None
    if found:
        return f"its timeout of {found[1]} min"
    return "its timeout" if check.get("conclusion") == "TIMED_OUT" else ""


def _rerun(half: Half) -> None:
    rerun(half.run, half.seen.world, {row["slug"] for row in half.rows or []})


STEPS = (verbs.Step("after-expedite", 25, "cancelled.rerun", _rerun, ("world",)),)
