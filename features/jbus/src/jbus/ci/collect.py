"""Ask GitHub for a project's Actions jobs and pull requests, and keep them (`jbus.ci.ledger`).

Every call is a read through `gh api`. The collector reads the repo's workflow runs created since a
time and the pull requests updated since then. For each run that completed it reads the jobs the
ledger does not keep yet, with `filter=all` so that it gets every attempt of a rerun. For each
pull request whose update the ledger has not kept, it reads the timeline, where a force-push of its
branch is an event: one the ledger kept at the same update keeps its force-pushes. The pull
requests come a page at a time, the latest update first, and the collector stops at the first page
that reaches back past the time. For a red job on a local runner it reads the log once, for the
failing tests the log names and the runner faults the log shows.

`jbus ci` collects the last `days` days (`collect`) and waits for the ledger's lock. Each pass of
jbus collects too (`keep`, from the step in `jbus.ci`): the runs created in the last `PASS_HOURS`
hours, at most `PASS_RUNS` new runs, so that a pass after a gap catches up over a few passes, and
the pull requests updated since the newest update the ledger holds, where that is earlier, back at
most `CATCH_UP`: a pass after a gap keeps every pull request merged in it. It never waits for the
lock: while `jbus ci` holds it, the pass collects nothing. A run that completes more than
`PASS_HOURS` after it was created is kept by the next `jbus ci`.

The collector reads a job's telemetry from its check run's annotations. Of a job's own words, the
API returns only its annotations, since the API cannot read a job summary. The telemetry is an
annotation titled `jstack-ci` whose message is a JSON object (`jbus.ci.notice` writes it).

`Gh` is the interface to GitHub: `Cli` asks GitHub through `gh`, by itself or through a pass's
own runner, and a test passes a `Gh` that replays a recording. An answer that is not JSON, or not
the shape the path gives, is `Unavailable`, as a GitHub that does not answer is.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import jsettings
from jbus import locked
from jbus.ci import ledger
from jmerge import budget as allowance

TITLE = "jstack-ci"
PAGE = 100
PASS_HOURS = 3
PASS_RUNS = 30
CATCH_UP = timedelta(days=14)
HOSTED = re.compile(r"^(ubuntu|windows|macos)-")
EVIDENCE = re.compile(r"^(FAILED|ERROR|E  |##\[error\])")
FAILING = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)")
SIGNS = {
    "bus": re.compile(
        r"(?i)failed to connect to (the |system |user )?bus|DBUS_SESSION_BUS_ADDRESS"
        r"|systemctl --user|systemd-analyze|No medium found|user bus|Failed t\.\.\."
    ),
    "browser": re.compile(
        r"(?i)(chromium|chrome)[^\n]{0,40}(not found|No such file)"
        r"|no (chromium|chrome|browser) (on|in|found)|could not find (chromium|chrome)"
        r"|browser did not finish"
    ),
    "space": re.compile(r"ENOSPC|No space left"),
}
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ")
ESCAPES = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Unavailable(Exception):
    """GitHub did not answer."""


class Gh(Protocol):
    """A `Gh` asks GitHub. `pages` returns the list GitHub gives for a path over every page, and
    `page` the list of its one page. When each page is an object, the list is under `key` in it."""

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]: ...

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]: ...

    def log(self, repo: str, job: int) -> str: ...


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise Unavailable(str(error)[:200]) from error


def _listed(page: Any, key: str | None) -> list[dict[str, Any]]:
    """The list of one page, under `key` where the page is an object."""
    found = (page.get(key) if isinstance(page, dict) else None) if key else page
    if not isinstance(found, list) or not all(isinstance(one, dict) for one in found):
        raise Unavailable("GitHub gave a page of another shape")
    return found


class Cli:
    """Ask GitHub through `gh api`, one call at a time, and only read. `ask` runs the command:
    by itself, or as a pass of jbus runs it, in the project's checkout."""

    def __init__(self, ask: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run):
        self.ask = ask

    def _said(self, *args: str) -> str:
        asked = self.ask(["gh", "api", *args])
        if asked.returncode and allowance.refused(asked.stderr):
            raise Unavailable(allowance.named(self.ask(allowance.ASK)))
        if asked.returncode:
            raise Unavailable(" ".join(asked.stderr.split())[:200] or f"gh exit {asked.returncode}")
        return asked.stdout

    def _json(self, *args: str) -> Any:
        try:
            return json.loads(self._said(*args))
        except ValueError as error:
            raise Unavailable("GitHub gave no JSON") from error

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        every = self._json(path, "--paginate", "--slurp")
        if not isinstance(every, list):
            raise Unavailable("GitHub gave no list of pages")
        return [one for page in every for one in _listed(page, key)]

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        return _listed(self._json(path), key)

    def log(self, repo: str, job: int) -> str:
        return self._said(f"repos/{repo}/actions/jobs/{job}/logs", "--allow-escape-sequences")


@dataclass(frozen=True)
class Counts:
    runs: int
    jobs: int
    pulls: int


def kind(labels: list[str]) -> str:
    return "hosted" if any(HOSTED.match(one) for one in labels) else "local"


def evidence(log: str) -> list[str]:
    """Return the lines of a job's log that say what failed, with the stamp removed and each
    line cut short."""
    lines = (STAMP.sub("", ESCAPES.sub("", one)).strip() for one in log.splitlines())
    return [one[:200] for one in lines if EVIDENCE.match(one)]


def failing_tests(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        named = FAILING.match(line)
        if named and named[1] not in found:
            found.append(named[1])
    return found


def signs(lines: list[str]) -> list[str]:
    return [name for name, rule in SIGNS.items() if any(rule.search(one) for one in lines)]


def _time(text: str | None) -> datetime | None:
    return jsettings.when(text) if text else None


def pull_for(run: dict[str, Any], job: dict[str, Any], pulls: list[dict[str, Any]]) -> int | None:
    """Return the pull request a job ran for: the one its run names, the one a push to main
    merged, or the one that was open on the run's branch when GitHub created the job."""
    named = run.get("pull_requests") or []
    if named:
        return int(named[0]["number"])
    branch, made = run.get("head_branch"), _time(job.get("created_at"))
    if run.get("event") == "push" and branch == "main":
        for one in pulls:
            if one.get("merge_commit") and one["merge_commit"] == run.get("head_sha"):
                return int(one["number"])
        return None
    for one in pulls:
        opened, ended = _time(one["created"]), _time(one["merged"] or one["closed"])
        if one["branch"] == branch and made and opened and opened <= made:
            if ended is None or made <= ended + timedelta(minutes=5):
                return int(one["number"])
    return None


def notice(gh: Gh, repo: str, job: int) -> dict[str, Any]:
    """Return the telemetry a job wrote, or nothing where it wrote none or GitHub did not
    answer."""
    try:
        found = gh.pages(f"repos/{repo}/check-runs/{job}/annotations?per_page=100")
    except Unavailable:
        return {}
    given: dict[str, Any] = {}
    for one in found:
        if one.get("title") != TITLE:
            continue
        try:
            said = json.loads(one.get("message") or "")
        except ValueError:
            continue
        if isinstance(said, dict):
            given.update({k: v for k, v in said.items() if k in ledger.TELEMETRY})
    return given


def row(
    gh: Gh, repo: str, run: dict[str, Any], job: dict[str, Any], pulls: list[dict[str, Any]]
) -> dict[str, Any]:
    labels = job.get("labels") or []
    steps = len(job.get("steps") or [])
    made: dict[str, Any] = {
        "run": run["id"],
        "job": job["id"],
        "attempt": job.get("run_attempt") or run.get("run_attempt") or 1,
        "name": job.get("name"),
        "sha": job.get("head_sha") or run.get("head_sha"),
        "branch": run.get("head_branch"),
        "pr": pull_for(run, job, pulls),
        "event": run.get("event"),
        "created": job.get("created_at"),
        "started": job.get("started_at") if steps else None,
        "completed": job.get("completed_at"),
        "conclusion": job.get("conclusion"),
        "runner": job.get("runner_name") or None,
        "kind": kind(labels),
        "steps": steps,
        "tests": [],
        "signs": [],
        **dict.fromkeys(ledger.TELEMETRY),
    }
    if steps:
        made.update(notice(gh, repo, job["id"]))
    if steps and made["kind"] == "local" and job.get("conclusion") == "failure":
        try:
            lines = evidence(gh.log(repo, job["id"]))
        except Unavailable:
            made["tests"] = None
        else:
            made["tests"], made["signs"] = failing_tests(lines), signs(lines)
    return made


def _pushes(gh: Gh, repo: str, number: int) -> list[str]:
    timeline = gh.pages(f"repos/{repo}/issues/{number}/timeline?per_page=100")
    return sorted(x["created_at"] for x in timeline if x.get("event") == "head_ref_force_pushed")


def pulls(
    gh: Gh, repo: str, since: datetime, held: dict[int, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Return the pull requests updated since `since`, each with the times someone
    force-pushed its branch. A page at a time, the latest update first, up to the first page
    that reaches back past `since`. One that `held` keeps at the same update keeps its
    force-pushes, and its timeline is not read again."""
    held = held or {}
    kept, number = [], 1
    while True:
        path = f"repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page={PAGE}"
        found = gh.page(f"{path}&page={number}")
        for one in found:
            stamp = one.get("updated_at")
            updated = _time(stamp or one.get("created_at"))
            if updated is not None and updated < since:
                continue
            was = held.get(one["number"], {})
            same = bool(stamp) and was.get("updated") == stamp
            kept.append(
                {
                    "number": one["number"],
                    "branch": one["head"]["ref"],
                    "head": one["head"]["sha"],
                    "created": one["created_at"],
                    "updated": stamp,
                    "merged": one.get("merged_at"),
                    "closed": one.get("closed_at"),
                    "merge_commit": one.get("merge_commit_sha") if one.get("merged_at") else None,
                    "pushes": was["pushes"] if same else _pushes(gh, repo, one["number"]),
                }
            )
        last = found[-1] if found else {}
        oldest = _time(last.get("updated_at") or last.get("created_at"))
        if len(found) < PAGE or (oldest is not None and oldest < since):
            return kept
        number += 1


def collect(gh: Gh, repo: str, state: Path, now: datetime, days: int) -> Counts:
    """Add to the ledger the jobs of the last `days` days that it does not have yet. Also keep
    the pull requests. It waits for another collector to end first."""
    with locked(state, ledger.LOCK):
        return _collect(gh, repo, state, now - timedelta(days=days))


def keep(gh: Gh, repo: str, state: Path, now: datetime) -> Counts | None:
    """What a pass collects: the runs of the last `PASS_HOURS` hours, at most `PASS_RUNS` new
    ones, and the pull requests updated since then or since the newest update the ledger holds,
    whichever is earlier, back at most `CATCH_UP`. None where another collector holds the
    ledger, which the pass does not wait for."""
    try:
        with locked(state, ledger.LOCK, wait=False):
            since = now - timedelta(hours=PASS_HOURS)
            return _collect(gh, repo, state, since, PASS_RUNS, now - CATCH_UP)
    except BlockingIOError:
        return None


def _collect(
    gh: Gh,
    repo: str,
    state: Path,
    since: datetime,
    most: int | None = None,
    back: datetime | None = None,
) -> Counts:
    """Keep the pull requests and the jobs of the runs created since `since`, of at most `most`
    new runs. With `back`, the pull requests are those updated since the newest update the
    ledger holds where that is earlier than `since`, and not before `back`. The pull requests'
    file is written only where one of them changed, and each run's jobs as soon as they are
    read, so a collector stopped half way keeps what it read."""
    held = {one["number"]: one for one in ledger.read(state / ledger.PULLS)}
    updated = [when for one in held.values() if (when := _time(one.get("updated")))]
    caught = since if back is None or not updated else max(back, min(since, max(updated)))
    now_held = held | {one["number"]: one for one in pulls(gh, repo, caught, held)}
    everyone = sorted(now_held.values(), key=lambda one: one["number"])
    if now_held != held:
        ledger.rewrite(state / ledger.PULLS, everyone)
    seen = {(one["run"], one["attempt"]) for one in ledger.read(state / ledger.JOBS)}
    stamp = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = gh.pages(
        f"repos/{repo}/actions/runs?per_page={PAGE}&created=%3E%3D{stamp}", "workflow_runs"
    )
    new = [
        run
        for run in runs
        if run.get("status") == "completed" and (run["id"], run.get("run_attempt") or 1) not in seen
    ]
    added = 0
    for run in new[:most]:
        rows = [
            row(gh, repo, run, job, everyone)
            for job in gh.pages(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=all", "jobs")
            if job.get("status") == "completed"
        ]
        added += ledger.add(state / ledger.JOBS, rows)
    return Counts(len(runs), added, len(everyone))
