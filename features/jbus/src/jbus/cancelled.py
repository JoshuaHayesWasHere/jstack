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
(`why`) while the check stays stopped at that head, less GitHub's refusal, which only the home
hears. Until then,
a row whose every failed check is of a run this module runs again is its own (`owns`), and no
blocker the home's `jbus clear` asks a fix for.

Only the head's own runs count. A check run whose job GitHub says ran on another commit belongs to
a head that a newer push displaced, and `rerun` neither runs it again nor tells anyone of it.

A required run GitHub queued and never started is this module's too (`unqueue`), on every open
row's pull request and not only on the one `jmerge` has at the head of its line. Where the
roll-up lists no run of a required check, or lists one queued for `ready.QUEUED_MINUTES`, it reads
the head's workflow runs and their jobs: GitHub lists no check of a run that has no jobs, so the
roll-up alone misses it (#1695, 2026-11-11). Each run `ready.stuck_runs` finds is cancelled where
it has not ended and run again, `gh run rerun <run>`, once for the head: the act is marked
`queued|<slug>|<head12>` in the outbox, with one quiet `queued` line. GitHub ends a cancel after it
answers and refuses to run again a run it has not ended, so a rerun it refused is asked again on
each pass, and the cancel too while the run has not ended, for `ready.RESTART_MINUTES` from the
first try; then it is given up, under the same mark, with GitHub's refusal on its line. A run
GitHub queues again at that head is not restarted again: it is logged once, and the wait is the
home's.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from jbus import read_json, verbs, write_json
from jbus.passes import Pass
from jbus.watch import NEVER, World, _api, _runs_of, job, job_log
from jmerge import ready
from jmerge.checks import check_state, latest_of_each

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"cancelled": "quiet", "queued": "quiet"}
STALL = "stall"
STOPPED = ("CANCELLED", "TIMED_OUT")
FILE = "cancelled.json"
QUEUED = "queued"
QUEUED_FILE = "queued.json"
"""Each slug's restart of its head's queued runs (`unqueue`): `head`, `asked` when it was first
tried, `runs` the attempt of each run it restarts by its id, `owed` the runs whose rerun has not
taken, `said` the line's start and `why` GitHub's last refusal."""
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
    kept = read_json(run.state / FILE, {}).get(slug) or {}
    told = kept["why"] if kept.get("head") == head else ""
    if attempt > 1:
        if told and _told(slug, head) in run.box.sent():
            return told
        part = stop.get("name") or stop.get("context") or name
        minutes = [_minutes(_before(run, repo, number, attempt, part)), _minutes(given)]
        cause = _cause(run, repo, at, stop)
        return _tell(run, slug, head, f"#{pr}: {twice(name, minutes, cause)}")
    key = f"rerun {number}"
    if f"cancelled|{slug}|{key}" in run.box.sent():
        return _tell(run, slug, head, f"#{pr}: {unrun(name, _minutes(given))}") if told else ""
    asked = run.run("gh", "run", "rerun", number, "--failed")
    if asked.returncode == 0:
        line = f"cancelled {slug}: ran #{pr}'s check again, run {number} at {head[:12]}"
        run.find(slug, "cancelled", line, key=key)
        run.say(line)
        return ""
    line = f"cancelled {slug}: GitHub did not run #{pr}'s check again, run {number} at {head[:12]}"
    run.find(slug, "cancelled", line, asked.stderr, key=key)
    refusal = (asked.stderr.strip().splitlines() or ["no reason given"])[0]
    return _tell(run, slug, head, f"#{pr}: {unrun(name, _minutes(given))}", refusal)


def twice(name: str, minutes: list[int | None], cause: str) -> str:
    """Return the reason of a check that was cancelled at two attempts (`ready.CANCELLED_TWICE`),
    with how long each attempt ran where GitHub says, and the cause where the job's log names
    one."""
    when = _at(minutes)
    said = ready.CANCELLED_TWICE.format(check=_part(name)) + ("," + when if when else "")
    return said + (f": {cause}" if cause else "")


def unrun(name: str, minutes: int | None) -> str:
    """Return the reason of a check that was cancelled and that GitHub did not run again
    (`ready.CANCELLED_UNRUN`), with how long it ran where GitHub says. GitHub's refusal is no part
    of it: the view shows the row's `why` as its reason, and a rate limit is not why it waits."""
    ran = _at([minutes]).removeprefix(" at")
    return ready.CANCELLED_UNRUN.format(check=_part(name)) + (f" (it ran{ran})" if ran else "")


def _part(name: str) -> str:
    return "check" if name == "check" else f"check {name}"


def _told(slug: str, head: str) -> str:
    return f"{STALL}|{slug}|{FILE} {head[:12]}"


def _tell(run: Pass, slug: str, head: str, line: str, refusal: str = "") -> str:
    """Log the slug's cancelled check as one quiet stall, once for the head: the one list takes it
    to the brief's home (`jbus.wakes`), and with no home the log is the one record. The home hears
    GitHub's `refusal` after the line, and the returned line, the row's `why`, leaves it out."""
    told = f"{line}: {refusal}" if refusal else line
    run.find(slug, STALL, f"{STALL} {slug}: {told}", key=f"{FILE} {head[:12]}")
    run.say(f"cancelled {slug}: {told}")
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


def unqueue(run: Pass, world: World, slugs: set[str]) -> None:
    """Cancel and run again, once for the head, each required run GitHub queued at an open row's
    pull request and started nothing of for `ready.QUEUED_MINUTES`, and log once a run it queues
    again there after that."""
    was: dict[str, dict] = read_json(run.state / QUEUED_FILE, {})
    kept: dict[str, dict] = {}
    names = required(run)
    for slug, pull in world.open.items():
        head = pull.get("headRefOid", "")
        if slug not in slugs or not head:
            continue
        mine = was.get(slug) if (was.get(slug) or {}).get("head") == head else None
        if mine is not None:
            kept[slug] = mine
        if not (mine and mine.get("owed")) and not _queued(pull, names, run.now):
            continue
        listed = _api(run, _runs_of(head)) or {}
        runs = [one for one in listed.get("workflow_runs") or [] if one.get("id")]
        key = f"{QUEUED}|{slug}|{head[:12]}"
        if key in run.box.sent():
            _again(run, slug, pull, mine or {}, _stuck(run, runs, names))
            continue
        if mine is None:
            stuck = _stuck(run, runs, names)
            if not stuck:
                continue
            mine = _asked(run, pull, stuck)
            kept[slug] = mine
            write_json(run.state / QUEUED_FILE, {**was, **kept})
        kept[slug] = _restart(run, slug, pull, mine, {str(one["id"]): one for one in runs})
    if kept != was:
        write_json(run.state / QUEUED_FILE, kept)


def _queued(pull: dict, names: tuple[str, ...], now: datetime) -> bool:
    """Whether the roll-up leaves the head's runs to be read: it lists no run of a required check,
    or lists one GitHub queued `ready.QUEUED_MINUTES` ago and started none of."""
    rollup = pull.get("statusCheckRollup") or []
    if any(not ready.latest(rollup, name) for name in names):
        return True
    bound = ready.QUEUED_MINUTES * 60
    return any((now - since).total_seconds() >= bound for _, since in ready.queued(rollup, names))


def _stuck(run: Pass, runs: list[dict], names: tuple[str, ...]) -> tuple[ready.StuckRun, ...]:
    """The required runs `ready.stuck_runs` finds at the head, with the jobs of each latest
    required run that has not passed, as GitHub gives them."""
    jobs: dict[str, list[dict]] = {}
    for name in names:
        mine = [one for one in runs if one.get("name") == name]
        last = max(mine, key=lambda one: int(one["id"]), default=None)
        if last is None or last.get("conclusion") == "success":
            continue
        path = f"repos/{{owner}}/{{repo}}/actions/runs/{last['id']}/jobs?per_page=100"
        given = _api(run, path)
        if isinstance(given, dict):
            jobs[str(last["id"])] = list(given.get("jobs") or [])
    return ready.stuck_runs(runs, jobs, names, run.now)


def _asked(run: Pass, pull: dict, stuck: tuple[ready.StuckRun, ...]) -> dict:
    """The record of a restart of `stuck`, kept before GitHub is asked anything, so a pass that
    stops between two asks leaves the next one the runs still owed."""
    minutes = int((run.now - min(one.since for one in stuck)).total_seconds() // 60)
    said = (
        f"GitHub queued #{pull['number']}'s {_runs(stuck)} at {pull['headRefOid'][:12]} "
        f"{minutes} minutes ago and started no job"
    )
    return {
        "head": pull["headRefOid"],
        "asked": run.now.isoformat(),
        "runs": {str(one.run): one.attempt for one in stuck},
        "owed": [str(one.run) for one in stuck],
        "cancels": any(not one.ended for one in stuck),
        "said": said,
    }


def _restart(run: Pass, slug: str, pull: dict, mine: dict, runs: dict[str, dict]) -> dict:
    """Ask GitHub for each rerun still owed, with a cancel first of a run that has not ended, and
    mark the head's restart done once none is owed, or given up `ready.RESTART_MINUTES` after its
    first try. Return the record as it then stands."""
    head, it = pull["headRefOid"], "them" if len(mine["runs"]) > 1 else "it"
    key = head[:12]
    if (run.now - datetime.fromisoformat(mine["asked"])).total_seconds() >= (
        ready.RESTART_MINUTES * 60
    ):
        line = (
            f"{QUEUED} {slug}: {mine['said']}, and did not run {it} again in "
            f"{ready.RESTART_MINUTES} minutes of tries: {mine.get('why') or 'no reason given'}"
        )
        if run.find(slug, QUEUED, line, key=key):
            run.say(line)
        return {**mine, "owed": []}
    owed = []
    why = mine.get("why", "")
    for number in mine["owed"]:
        if (runs.get(number) or {}).get("status", "completed") != "completed":
            run.run("gh", "run", "cancel", number)
        asked = run.run("gh", "run", "rerun", number)
        if asked.returncode:
            owed.append(number)
            why = (asked.stderr.strip().splitlines() or ["no reason given"])[0]
    if owed:
        return {**mine, "owed": owed, "why": why}
    done = f"cancelled {it} and ran {it} again" if mine.get("cancels") else f"ran {it} again"
    line = f"{QUEUED} {slug}: {mine['said']}: {done}"
    if run.find(slug, QUEUED, line, key=key):
        run.say(line)
    return {**mine, "owed": []}


def _again(run: Pass, slug: str, pull: dict, mine: dict, stuck: tuple[ready.StuckRun, ...]) -> None:
    """Log once a run GitHub queued at the head again after its restart: jbus restarts no run
    twice at a head, and the wait is the home's."""
    restarted = mine.get("runs") or {}
    again = [one for one in stuck if one.attempt > int(restarted.get(str(one.run), 0))]
    if not again:
        return
    it = "them" if len(again) > 1 else "it"
    line = (
        f"{QUEUED} {slug}: GitHub queued #{pull['number']}'s {_runs(tuple(again))} at "
        f"{pull['headRefOid'][:12]} again after jbus ran {it} again, and started no job in "
        f"{ready.QUEUED_MINUTES} minutes: jbus restarts no run twice at a head"
    )
    if run.find(slug, QUEUED, line, key=f"{pull['headRefOid'][:12]} again"):
        run.say(line)


def _runs(stuck: tuple[ready.StuckRun, ...]) -> str:
    names = [one.check for one in stuck]
    named = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"{named} run" + ("s" if len(names) > 1 else "")


def _rerun(half: Half) -> None:
    world = half.seen.world
    if world is not None:
        rerun(half.run, world, {row["slug"] for row in half.rows or []})


def _unqueue(half: Half) -> None:
    world = half.seen.world
    if world is not None:
        unqueue(half.run, world, {row["slug"] for row in half.rows or []})


STEPS = (
    verbs.Step("after-expedite", 25, "cancelled.rerun", _rerun, ("world",)),
    verbs.Step("after-expedite", 26, "cancelled.unqueue", _unqueue, ("world",)),
)
