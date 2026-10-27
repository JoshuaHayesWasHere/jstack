"""What `jbus flow` reads, as plain records: the events of each project, jbus's journal, and
GitHub's runs, jobs and merged pull requests.

Each reader takes text or JSON that a command printed and returns records, so a test drives it
on fixture text with no command run. `ask` is the one function that runs a command, and it runs
only commands that read: `journalctl`, `git remote get-url` and `gh` with `pr list` and `api` on
a `GET` address. The jobs of each run are a call per run, so they are asked for only on
`--jobs`, and only when the calls leave at least half of GitHub's hourly budget, which jbus's
own passes share, and above the floor of `jbus.budget` (`affordable`).

A row's `Sighting` is what a table of the event log said of it at one time: its status, its
checks, its pull request, its thread, the rows it depends on or merges after, why it waits, and
the event that said it (`source`), so each span `jbus.flow.measure` cuts names the record it
came from. The log writes a table each time a row changes (`queue ...: the table changed`) and
once a day whole (`snapshot`). A `Said` is a line `jmerge` logged of a pull request, read with
`jmerge.lines.one`: it changes why the row waits and nothing else. A `Mark` is an item's line
that a row's pull request waits on the owner's merge (`waiting: ... is hold`) or went back to
its checks (`resumed: ... is check`): the table writes a row's line only when a column of its
own changes, so these lines say a hold the table did not.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsettings
from jbus import budget
from jmerge import lines

ZONES = {"EDT": timezone(timedelta(hours=-4)), "EST": timezone(timedelta(hours=-5))}
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (EDT|EST)")
MERGED = re.compile(r"^merged (\S+) #(\d+)")
CAPPED = re.compile(r"^capped (\S+): (\S+) is capped until (\S+)")
BOTH = re.compile(r"^stall (\S+): (\S+) and (\S+) are both capped until (\S+)")
SLOT = re.compile(
    r"^slot-wake: woke (\S+), a (\w+) slot is free for `([^`]*)`(?:, after (\d+) min)?"
)
POOL = re.compile(
    r"^pool-wake: woke (\S+), the review pool was capped until (\S+), after (\d+) min"
)
WORKTREE = re.compile(r"/worktrees/([^/\s]+)/")
ITEM = re.compile(r"^item \S+: w\d+ (\w+): row (\S+) (?:(?:is|was) (\w+)|has a go: (.*))$")
MARKS = {"hold": "hold: needs the owner (the item waits)", "check": ""}
"""What an item's `waiting` or `resumed` line says of a row's pull request: a hold for the owner,
or back to its checks, where the why `jmerge` gave last stands again."""
ITEM_STATES = {
    "behind": ("queued", "behind: the rows in front of it to merge"),
    "ready": ("queued", "ready: the next pass of jbus to launch it"),
    "unapproved": ("queued", "not approved"),
    "launching": ("launched", ""),
    "removed": ("removed", ""),
}
"""What an item's line says of a row that its tables do not: the status and why of a row before
its launch. An item is `behind` while the rows in front of it merge, and `ready` until a pass
launches it. A row that `was removed` is over, as a merged one is."""
TIMEOUT = 120


@dataclass(frozen=True)
class Sighting:
    """What one table said of a row at `at`."""

    at: datetime
    status: str
    checks: str
    why: str
    pr: str
    thread: str
    approved: str
    depends: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True)
class Said:
    """A line `jmerge` logged of pull request `number` at `at`: `verdict` is its first word."""

    at: datetime
    number: str
    verdict: str
    why: str
    source: str = ""


@dataclass(frozen=True)
class Mark:
    """An item's line at `at` that the row's pull request waits on the owner or on its checks."""

    at: datetime
    slug: str
    why: str
    source: str


@dataclass(frozen=True)
class Cap:
    """An account that could not run `slug` from `at` until `until`."""

    at: datetime
    until: datetime
    slug: str
    accounts: tuple[str, ...]


@dataclass(frozen=True)
class SlotWait:
    """A thread that waited `minutes` for a test slot (`kind` full or short), told at `at`."""

    at: datetime
    minutes: int
    kind: str
    slug: str
    thread: str


@dataclass
class Project:
    """Everything the event log of one project holds that `jbus flow` measures."""

    name: str
    sightings: dict[str, list[Sighting]] = field(default_factory=dict)
    said: list[Said] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    merged: dict[str, tuple[datetime, str]] = field(default_factory=dict)
    caps: list[Cap] = field(default_factory=list)
    slots: list[SlotWait] = field(default_factory=list)
    pool: list[tuple[datetime, int]] = field(default_factory=list)
    pages: list[tuple[datetime, str]] = field(default_factory=list)
    approvals: dict[str, datetime] = field(default_factory=dict)
    first: datetime | None = None


@dataclass(frozen=True)
class Line:
    """One line of jbus's journal."""

    at: datetime
    text: str


@dataclass(frozen=True)
class Run:
    """One run of a GitHub Actions workflow, with its jobs' queue and run seconds."""

    repo: str
    id: int
    workflow: str
    event: str
    branch: str
    conclusion: str
    attempt: int
    created: datetime
    started: datetime | None
    updated: datetime | None
    queued: tuple[float, ...] = ()
    ran: tuple[float, ...] = ()
    hosted: tuple[bool, ...] = ()


def when(text: str) -> datetime | None:
    """Return the ISO 8601 time, aware, or None for an empty or odd string."""
    try:
        moment = jsettings.when(text)
    except (ValueError, TypeError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def stamped(text: str) -> datetime | None:
    """Return the first `YYYY-MM-DD HH:MM EDT` time in the text, as the tables write one."""
    found = STAMP.search(text or "")
    if not found:
        return None
    return datetime.strptime(found[1], "%Y-%m-%d %H:%M").replace(tzinfo=ZONES[found[2]])


def tables(text: str) -> Iterable[dict[str, str]]:
    """Yield each row of each markdown table in the text, by its header's names."""
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [one.strip() for one in line.strip().strip("|").split("|")]
        if cells and cells[0] == "slug":
            header = cells
        elif header and not set(cells[0]) <= {"-", " "} and len(cells) == len(header):
            yield dict(zip(header, cells, strict=True))


def events(name: str, lines: Iterable[str]) -> Project:
    """Read a project's `events.jsonl`. A line that does not parse is skipped."""
    project = Project(name)
    for raw in lines:
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        at = when(record.get("at", "")) if isinstance(record, dict) else None
        if at is None or "event" not in record:
            continue
        project.first = min(project.first or at, at)
        _event(project, at, record)
    return project


def _event(project: Project, at: datetime, record: dict[str, Any]) -> None:
    kind, line, text = record["event"], record.get("line", ""), record.get("text", "")
    source = f"{project.name} events.jsonl {record['at']} {kind}"
    if record.get("loud") == "user":
        project.pages.append((at, kind))
    if kind in ("queue", "snapshot"):
        for row in tables(text):
            seen = Sighting(
                at,
                row.get("status", ""),
                row.get("checks", ""),
                row.get("why", ""),
                row.get("pr", "").lstrip("#"),
                row.get("thread", ""),
                row.get("approved", ""),
                _slugs(row.get("depends", "") + "," + row.get("merge_after", "")),
                source,
            )
            project.sightings.setdefault(row["slug"], []).append(seen)
    elif kind.startswith("item.") and (found := ITEM.match(line)):
        _item(project, at, found[2], found[3], found[4], source)
    elif kind == "jmerge" and (said := lines.one(line)):
        project.said.append(Said(at, str(said.number), said.word, said.reason, source))
    elif kind == "merged" and (found := MERGED.match(line)):
        project.merged.setdefault(found[1], (at, found[2]))
    elif kind == "stall" and (found := CAPPED.match(line)):
        _cap(project, at, found[3], found[1], (found[2],))
    elif kind == "stall" and (found := BOTH.match(line)):
        _cap(project, at, found[4], found[1], (found[2], found[3]))
    elif kind == "slot-wake" and (found := SLOT.match(line)):
        place = WORKTREE.search(found[3])
        slug = place[1] if place else ""
        project.slots.append(SlotWait(at, int(found[4] or 0), found[2], slug, found[1]))
    elif kind == "pool-wake" and (found := POOL.match(line)):
        project.pool.append((at, int(found[3])))


def _slugs(cell: str) -> tuple[str, ...]:
    """Return the slugs of a `depends` or `merge_after` cell, each once, in order."""
    return tuple(dict.fromkeys(one.strip() for one in cell.split(",") if one.strip()))


def _item(
    project: Project, at: datetime, slug: str, value: str | None, go: str | None, source: str
) -> None:
    if go is not None:
        stamp = stamped(go)
        if stamp is not None and slug not in project.approvals:
            project.approvals[slug] = stamp
    elif value in MARKS:
        project.marks.append(Mark(at, slug, MARKS[value], source))
    elif value in ITEM_STATES:
        status, why = ITEM_STATES[value]
        seen = Sighting(at, status, "", why, "", "", "", (), source)
        project.sightings.setdefault(slug, []).append(seen)


def _cap(project: Project, at: datetime, until: str, slug: str, who: tuple[str, ...]) -> None:
    end = when(until)
    if end is not None and end > at:
        project.caps.append(Cap(at, end, slug, who))


def journal(text: str) -> list[Line]:
    """Read `journalctl -o short-iso` text: each line's time and what follows its `name[pid]:`."""
    found = []
    for raw in text.splitlines():
        stamp, _, rest = raw.partition(" ")
        at = when(stamp)
        if at is None:
            continue
        _, _, said = rest.partition(": ")
        found.append(Line(at, said))
    return found


def runs(repo: str, listed: Iterable[dict[str, Any]], jobs: dict[int, list[dict]]) -> list[Run]:
    """Read the REST `actions/runs` objects of a repo, with each run's jobs where known."""
    made = []
    for one in listed:
        created = when(one.get("created_at", ""))
        if created is None:
            continue
        queued, ran, hosted = [], [], []
        for job in jobs.get(one["id"], []):
            made_at, began, ended = (when(job.get(key) or "") for key in JOB_TIMES)
            if began and made_at and job.get("conclusion") != "skipped":
                queued.append(max(0.0, (began - made_at).total_seconds()))
                ran.append(max(0.0, ((ended or began) - began).total_seconds()))
                hosted.append("self-hosted" not in (job.get("labels") or []))
        began, ended = when(one.get("run_started_at") or ""), when(one.get("updated_at") or "")
        if one["id"] not in jobs and began and ended:
            ran.append(max(0.0, (ended - began).total_seconds()))
        made.append(
            Run(
                repo,
                one["id"],
                one.get("name") or "",
                one.get("event") or "",
                one.get("head_branch") or "",
                one.get("conclusion") or one.get("status") or "",
                int(one.get("run_attempt") or 1),
                created,
                began,
                ended,
                tuple(queued),
                tuple(ran),
                tuple(hosted),
            )
        )
    return made


JOB_TIMES = ("created_at", "started_at", "completed_at")


def ask(command: list[str], cwd: Path | None = None) -> str | None:
    """Run a command that reads and return what it printed, or None where it failed."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, cwd=cwd, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def repo_of(checkout: Path) -> str | None:
    """Return `owner/name` of the checkout's `origin` on GitHub, or None."""
    url = (ask(["git", "-C", str(checkout), "remote", "get-url", "origin"]) or "").strip()
    found = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return found[1] if found else None


def github_runs(repo: str, since: datetime, until: datetime, jobs: bool) -> list[Run] | None:
    """Ask GitHub for every run of the repo created in the window, a day at a time so that no
    day passes the 1,000 runs a query returns, and each run's jobs when `jobs` is set."""
    listed: list[dict[str, Any]] = []
    day = since.astimezone(UTC).date()
    while day <= until.astimezone(UTC).date():
        said = ask(
            [
                "gh",
                "api",
                "--method",
                "GET",
                "--paginate",
                f"repos/{repo}/actions/runs?per_page=100&created={day.isoformat()}",
                "--jq",
                ".workflow_runs[]",
            ]
        )
        if said is None:
            return None
        listed += [json.loads(one) for one in said.splitlines() if one.strip()]
        day += timedelta(days=1)
    listed = [one for one in listed if since <= (when(one["created_at"]) or since) <= until]
    found: dict[int, list[dict]] = {}
    if jobs and not affordable(len(listed)):
        raise Unaffordable(repo, len(listed))
    if jobs:
        from concurrent.futures import ThreadPoolExecutor

        def one_run(run_id: int) -> tuple[int, list[dict]]:
            said = ask(["gh", "api", "--method", "GET", f"repos/{repo}/actions/runs/{run_id}/jobs"])
            return run_id, (json.loads(said).get("jobs", []) if said else [])

        with ThreadPoolExecutor(8) as pool:
            found = dict(pool.map(one_run, [one["id"] for one in listed]))
    return runs(repo, listed, found)


class Unaffordable(Exception):
    """Asking for each run's jobs would spend more than `SHARE` of what GitHub has left, or take
    it to the floor (`jbus.budget`)."""

    def __init__(self, repo: str, runs: int) -> None:
        super().__init__(
            f"refused: the jobs of {repo}'s {runs} runs are a call each, more than "
            f"{SHARE:.0%} of the GitHub calls left this hour or past the floor of "
            f"{budget.FLOOR} kept for merges, which every pass of jbus and every thread share: "
            "run again without --jobs, or later"
        )


SHARE = 0.5


def affordable(calls: int) -> bool:
    """Return whether `calls` more calls leave GitHub's hourly budget at least half full, and
    above the floor that jbus and the threads keep (`jbus.budget`). Asking for the budget is
    itself free."""
    left = budget.read(ask)
    return left is not None and not budget.held(left, calls) and calls <= left.low.remaining * SHARE


def github_merges(repo: str, since: datetime) -> dict[str, datetime] | None:
    """Return when each pull request of the repo merged at or after `since`, by its number."""
    said = ask(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--limit",
            "1000",
            "--search",
            f"merged:>={since.astimezone(UTC).date().isoformat()}",
            "--json",
            "number,mergedAt",
        ]
    )
    if said is None:
        return None
    found = {}
    for one in json.loads(said):
        at = when(one.get("mergedAt") or "")
        if at is not None:
            found[str(one["number"])] = at
    return found
