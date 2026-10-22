"""Ask GitHub for a project's Actions jobs and pull requests, and keep them (`jbus.ci.ledger`).

Every call is a read through `gh api`. It reads the repo's workflow runs of the last `days`
days, the jobs of each run the ledger does not keep yet (`filter=all`, so every attempt of a
rerun), and the pull requests. For each pull request it reads the timeline, where a
force-push of its branch is an event. For a red job on a local runner it reads the log once,
for the failing tests the log names and the runner faults it shows.

The collector reads a job's telemetry from its check run's annotations. An annotation is the
one place for a job's own words that the API returns, since the API cannot read a job
summary. The telemetry is an annotation titled `jstack-ci` whose message is a JSON object
(`jbus.ci.notice` writes it).

`Gh` is the interface to GitHub: `Cli` asks GitHub, and a test passes one that answers from
a recording.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from jbus.ci import ledger

TITLE = "jstack-ci"
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
    """`pages` returns the list a path gives, under `key` where each page is an object."""

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]: ...

    def log(self, repo: str, job: int) -> str: ...


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise Unavailable(str(error)[:200]) from error


class Cli:
    """Ask GitHub through `gh api`, one call at a time, and only read."""

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        asked = _run(["gh", "api", "--paginate", "--slurp", path])
        if asked.returncode:
            raise Unavailable(" ".join(asked.stderr.split())[:200] or f"gh exit {asked.returncode}")
        found: list[dict[str, Any]] = []
        for page in json.loads(asked.stdout):
            found.extend(page[key] if key else page)
        return found

    def log(self, repo: str, job: int) -> str:
        asked = _run(
            ["gh", "api", "--allow-escape-sequences", f"repos/{repo}/actions/jobs/{job}/logs"]
        )
        if asked.returncode:
            raise Unavailable(" ".join(asked.stderr.split())[:200] or f"gh exit {asked.returncode}")
        return asked.stdout


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
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def pull_for(run: dict[str, Any], job: dict[str, Any], pulls: list[dict[str, Any]]) -> int | None:
    """Return the pull request a job ran for: the one its run names, the one a push to main
    merged, or the one whose branch the run is of and which was open when GitHub created the
    job."""
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


def pulls(gh: Gh, repo: str, since: datetime) -> list[dict[str, Any]]:
    """Return the pull requests updated since `since`, each with the times someone
    force-pushed its branch."""
    found = gh.pages(f"repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100")
    kept = []
    for one in found:
        updated = _time(one.get("updated_at") or one.get("created_at"))
        if updated is not None and updated < since:
            continue
        timeline = gh.pages(f"repos/{repo}/issues/{one['number']}/timeline?per_page=100")
        kept.append(
            {
                "number": one["number"],
                "branch": one["head"]["ref"],
                "head": one["head"]["sha"],
                "created": one["created_at"],
                "merged": one.get("merged_at"),
                "closed": one.get("closed_at"),
                "merge_commit": one.get("merge_commit_sha") if one.get("merged_at") else None,
                "pushes": sorted(
                    x["created_at"] for x in timeline if x.get("event") == "head_ref_force_pushed"
                ),
            }
        )
    return kept


def collect(gh: Gh, repo: str, state: Path, now: datetime, days: int) -> Counts:
    """Keep the jobs of the last `days` days that the ledger does not have yet, and the pull
    requests."""
    with ledger.locked(state):
        return _collect(gh, repo, state, now, days)


def _collect(gh: Gh, repo: str, state: Path, now: datetime, days: int) -> Counts:
    since = now - timedelta(days=days)
    held = {one["number"]: one for one in ledger.read(state / ledger.PULLS)}
    for one in pulls(gh, repo, since):
        held[one["number"]] = one
    everyone = sorted(held.values(), key=lambda one: one["number"])
    ledger.rewrite(state / ledger.PULLS, everyone)
    kept = ledger.read(state / ledger.JOBS)
    seen = {(one["run"], one["attempt"]) for one in kept}
    runs = gh.pages(
        f"repos/{repo}/actions/runs?per_page=100&created=%3E%3D{since:%Y-%m-%d}", "workflow_runs"
    )
    added = 0
    for run in runs:
        if run.get("status") != "completed" or (run["id"], run.get("run_attempt") or 1) in seen:
            continue
        rows = [
            row(gh, repo, run, job, everyone)
            for job in gh.pages(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=all", "jobs")
            if job.get("status") == "completed"
        ]
        added += ledger.add(state / ledger.JOBS, rows)
    return Counts(len(runs), added, len(everyone))
