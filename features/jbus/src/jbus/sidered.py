"""`owe` gives each workflow that is red on main, and that no other rule of jbus's reads, one fix
row that owns the red.

jbus judges main by the check runs of its tip (`watch._check`, `watch._retro`, `mainmoved`), and
each nightly workflow by its own runs (`watch._nightly_red`). A workflow whose red run on main
leaves no check run at main's tip stays red with nobody's row on it:

- a run GitHub started no job for, since it could not read the workflow's file (jstack's
  release.yml ran no job in 8 of its 8 push runs on 2026-10-21);
- a run of a schedule or a manual run (pstack-drift.yml);
- a push run at a commit that is no longer main's tip (a workflow with path filters that did
  not run again).

`judge` reads one workflow's own runs on the default branch, newest first. The workflow is red
when its last run that passed or failed within `WINDOW` failed: a run cancelled or skipped says
nothing, and while a run of it is still going nothing is judged, since that run's answer is the
newest (the gate's run at a new tip, below which the last red would look like a side red). Nor
is anything judged while a push run of it at main's tip was cancelled: `watch._check` holds that
tip pending and runs it again, so its answer is still to come. A red is left to the gate's rule,
as before, when its newest run is a push run at main's tip that ran a job. It is left to the
account (S9's class) when its runs ran no job and neither did any other workflow's run on main
since. Every other red is a `Red`: `FAILED` when one
of its runs ran a job, and `NOT_RUN` when none did, which is a file GitHub cannot run, so its fix
is the file, or the workflow's removal where nothing needs it. jbus removes no workflow. A run
ran no job when it failed within `NO_JOB` of its start, as `jbus flow` counts it.

A red stands only while the workflow's file is the one its newest red run ran (`stands`). A
commit to the file on main since is a fix that no run has judged yet: release.yml's fix made it
run on a pushed tag alone, so no run on main ever ends its red. Such a red waits for the next
run of the workflow on main, and files nothing.

`owe` files one brief for each red, named for the workflow and the commit of the run that turned
it red, and queues it unapproved, as `_nightly_red` does: the user approves it like any other
row. `workflows.json` keeps, for each workflow, the row its red got and the red runs it has seen.
A red that shares a run with them is the same red, though its oldest run has slid out of the
`RUNS` that GitHub lists: it is not filed again, nor is it after its row was removed. A red that
a green run ended, and a new failure began, is a new row. On a
project's first pass `owe` only records the reds it sees. It asks GitHub at most once in `EVERY`,
since a pass runs each minute and a side workflow runs a few times a day.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jbus import Refused, queue, read_json, verbs, write_json
from jbus.flow.measure import NO_JOB
from jbus.passes import Pass
from jbus.watch import (
    NIGHTLIES,
    NOT_RED,
    Failed,
    _api,
    _default_branch,
    _log_failed,
    tests_said,
    when,
)

NAME = "workflows.json"
PREFIX = "workflow-red-"
FILES = ".github/workflows/"
EVERY = timedelta(minutes=15)
WINDOW = timedelta(days=3)
RUNS = 20
IDLE = ("cancelled", "skipped")
FAILED, NOT_RUN = "failed", "ran no job"
_STEM = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class Red:
    """A workflow red on main that no other rule owns. `runs` is its red runs, newest first:
    the last of them turned it red. `kind` is `FAILED` or `NOT_RUN`."""

    path: str
    kind: str
    runs: tuple[dict[str, Any], ...]

    @property
    def file(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def first(self) -> dict[str, Any]:
        return self.runs[-1]

    @property
    def name(self) -> str:
        stem = _STEM.sub("-", self.file.lower().removesuffix(".yml").removesuffix(".yaml"))
        return f"{PREFIX}{stem.strip('-.') or 'workflow'}-{self.first.get('head_sha', '')[:12]}"


def _ended(one: dict[str, Any]) -> datetime:
    return when(one.get("updated_at") or one["created_at"])


def _order(one: dict[str, Any]) -> tuple[datetime, int]:
    """Order runs by when they ended, and runs that ended at once by their id, as GitHub
    numbers them."""
    return _ended(one), int(one.get("id") or 0)


def _red(one: dict[str, Any]) -> bool:
    return one.get("conclusion") not in NOT_RED


def ran_a_job(one: dict[str, Any]) -> bool:
    """Return whether GitHub ran a job for the run: a run that passed did, one cancelled or
    skipped says nothing, and one that failed within `NO_JOB` of its start did not."""
    if one.get("status") != "completed" or one.get("conclusion") in IDLE:
        return False
    began = when(one.get("run_started_at") or one["created_at"])
    return not _red(one) or _ended(one) - began >= NO_JOB


def _pushed_at(one: dict[str, Any], tip: str) -> bool:
    return one.get("event") == "push" and one.get("head_sha") == tip


def judge(
    path: str, runs: list[dict[str, Any]], others: list[dict[str, Any]], tip: str, now: datetime
) -> Red | None:
    """Return the red of the workflow at `path` that no other rule owns, or None. `runs` is its
    runs on the default branch, one still going included, `others` the other workflows' runs
    there, and `tip` main's commit now."""
    if any(one.get("status") != "completed" for one in runs) or any(
        _pushed_at(one, tip) and one.get("conclusion") == "cancelled" for one in runs
    ):
        return None
    settled = sorted((one for one in runs if one.get("conclusion") not in IDLE), key=_order)[::-1]
    if not settled or now - _ended(settled[0]) > WINDOW:
        return None
    streak = tuple(itertools.takewhile(_red, settled))
    if not streak:
        return None
    newest = streak[0]
    if _pushed_at(newest, tip) and ran_a_job(newest):
        return None
    if any(ran_a_job(one) for one in streak):
        return Red(path, FAILED, streak)
    began = when(streak[-1]["created_at"])
    if not any(ran_a_job(one) and when(one["created_at"]) >= began for one in others):
        return None
    return Red(path, NOT_RUN, streak)


def stands(red: Red, changed: datetime | None) -> bool:
    """Return whether `red` still stands, where `changed` is when a commit to its workflow's
    file last landed on main, or None where none did lately."""
    return changed is None or changed <= when(red.runs[0]["created_at"])


def _changed(run: Pass, red: Red, default: str) -> tuple[bool, datetime | None]:
    """Return whether GitHub answered, and when the newest commit to `red`'s file on main was
    made."""
    path = f"repos/{{owner}}/{{repo}}/commits?path={red.path}&sha={default}&per_page=1"
    said = _api(run, path)
    if not isinstance(said, list):
        return False, None
    dates = [one["commit"]["committer"]["date"] for one in said if isinstance(one, dict)]
    return True, when(dates[0]) if dates else None


def brief(red: Red, day: str, jobs: list[tuple[str, str, Failed]]) -> str:
    """Return the brief for the fix of `red`, in the shape of `features/jbriefs/templates/brief.md`.
    `jobs` is each failed job's name, URL and failed tests, of the newest red run."""
    tests = [test for _, _, failed in jobs for test in failed.tests]
    where = ", ".join(
        f"`{file}`" for file in dict.fromkeys([red.path, *(t.split("::")[0] for t in tests)])
    )
    runs = len(red.runs)
    if red.kind == NOT_RUN:
        done = [
            f"- GitHub runs a job of {red.file} on main again: its file is one GitHub can read, "
            "or, where nothing needs the workflow, it is removed (it is a candidate for "
            "removal, and jbus removes no workflow)",
            "- the Result says which, and why GitHub could not run the file",
        ]
        said = f"GitHub started no job in {runs} runs on main since {day}"
    else:
        done = [
            f"- each failed job named under Read passes in a run of {red.file} on main",
            "- the Result names the cause: the merge that broke it, or a flake with its evidence",
        ]
        said = f"{runs} runs failed on main since {day}, {tests_said(jobs)}"
    read = [
        f"- the job `{job}`, {url or 'with no URL'}: "
        + (
            ", ".join(f"`{test}`" for test in failed.tests)
            or "its log names no failed test, read it"
        )
        for job, url, failed in jobs
    ]
    read += [
        f"- the run {one.get('html_url') or one.get('id')}, from {one.get('event') or 'an event'}, "
        f"at {one.get('head_sha')}"
        for one in red.runs
    ]
    return "\n".join(
        [
            f"# {red.name}: {red.file} is red on main since {day}",
            f'Task: "{red.file}: {said}" (jbus, from {red.path})',
            "Done when:",
            *done,
            f"Proves it: `gh run list --workflow {red.file} --branch main` shows a run that "
            "passed after the fix merged, or the workflow is gone from main",
            "Size: S",
            f"Where: {where}",
            "Do not touch: the ruleset",
            "Decisions: none, jbus filed this from a red workflow on main and the user has not "
            "seen it",
            "Design: none, a fix to what the red runs name",
            "Pull request: open one when done",
            "Review: review",
            "Playbook: bug-fix",
            "Read:",
            *read,
            "",
        ]
    )


def _jobs(run: Pass, red: Red) -> list[tuple[str, str, Failed]]:
    """Return each failed job of the newest red run, with its URL and the tests its log names."""
    if red.kind == NOT_RUN:
        return []
    number = red.runs[0].get("id")
    asked = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs/{number}/jobs?per_page=100")
    failed = [
        job
        for job in (asked if isinstance(asked, dict) else {}).get("jobs") or []
        if job.get("status") == "completed" and job.get("conclusion") not in NOT_RED
    ]
    return [
        (
            job.get("name") or "?",
            job.get("html_url") or "",
            _log_failed(run, job.get("id")) or Failed(),
        )
        for job in failed
    ]


def _line(red: Red, day: str, jobs: list[tuple[str, str, Failed]]) -> str:
    runs = f"{len(red.runs)} run{'s' if len(red.runs) > 1 else ''} since {day}"
    if red.kind == NOT_RUN:
        why = "GitHub could not run it, so fix its file or remove it"
        return f"retro {red.name}: {red.file} ran no job on main in {runs}: {why}"
    return f"retro {red.name}: {red.file} failed on main in {runs}, {tests_said(jobs)}"


def owe(run: Pass) -> None:
    """File and queue one brief for each workflow red on main that no other rule owns."""
    kept: dict[str, Any] = read_json(run.state / NAME, {})
    if kept.get("asked") and run.now - when(kept["asked"]) < EVERY:
        return
    listed = _api(run, "repos/{owner}/{repo}/actions/workflows?per_page=100")
    flows = [
        flow
        for flow in (listed.get("workflows") if isinstance(listed, dict) else None) or []
        if str(flow.get("path", "")).startswith(FILES)
        and flow.get("state") == "active"
        and flow["path"] not in {FILES + nightly.file for nightly in NIGHTLIES}
    ]
    default = _default_branch(run)
    asked = run.run("git", "ls-remote", "origin", f"refs/heads/{default}")
    tip = (asked.stdout.split() or [""])[0]
    if not isinstance(listed, dict) or asked.returncode != 0 or not tip:
        return
    runs: dict[str, list[dict[str, Any]]] = {}
    for flow in flows:
        path = f"repos/{{owner}}/{{repo}}/actions/workflows/{flow['id']}/runs"
        said = _api(run, f"{path}?branch={default}&per_page={RUNS}")
        if not isinstance(said, dict):
            return
        runs[flow["path"]] = [
            one
            for one in said.get("workflow_runs") or []
            if one.get("head_branch") == default
            and not str(one.get("event")).startswith("pull_request")
        ]
    filed: dict[str, dict[str, Any]] = kept.get("filed", {})
    for path, own in runs.items():
        others = [one for other, each in runs.items() if other != path for one in each]
        red = judge(path, own, others, tip, run.now)
        if red is None:
            continue
        ids = [str(one.get("id")) for one in red.runs]
        was = filed.get(path, {})
        if set(ids) & set(was.get("runs", [])):
            filed[path] = {"slug": was.get("slug", ""), "runs": ids}
            continue
        answered, changed = _changed(run, red, default)
        if not answered or not stands(red, changed):
            continue
        if (
            not run.first
            and red.name not in run.removed
            and queue.fresh(run.state, red.name) is None
        ):
            day = run.user.day(when(red.first["created_at"]))
            jobs = _jobs(run, red)
            text = brief(red, day, jobs)
            (run.home / "tasks").mkdir(parents=True, exist_ok=True)
            (run.home / "tasks" / f"{red.name}.md").write_text(text)
            try:
                queue.add(run.state, red.name, 0, [], text)
            except (Refused, queue.Unparsable) as refused:
                run.condition(red.name, f"its brief was not queued: {refused}")
                continue
            run.find(
                red.name,
                "retro",
                _line(red, day, jobs),
                key=f"workflow {red.first.get('id')}",
                past=True,
            )
        filed[path] = {"slug": red.name, "runs": ids}
    write_json(run.state / NAME, {"asked": run.now.isoformat(), "filed": filed})


STEPS = (verbs.Step("tellers", 45, "sidered.owe", lambda half: owe(half.run), ("budget",)),)
