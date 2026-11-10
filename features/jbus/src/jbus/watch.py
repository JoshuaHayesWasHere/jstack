"""This module asks T3 Code and GitHub for the work that is out, and writes each finding as
one line.

`look` asks once a pass for the project's crewmate threads, its open pull requests and the ones
merged lately. `look` counts the threads of a slug that was removed from the queue, but leaves them
out of its answer, so no pass finds such a thread stale or tells it to carry on. The slug's pull
requests stay in the answer. When only GitHub was silent, the answer from `look` still gives how
many crews are out. The machine has one such count: `jbus poll` adds it up over every project.
`watch` sends a line for what a home would have seen: a merge; a thread that ran past its
timebox, waits on a request, or ended with no Result and on no wait that jbus owns
(`World.awaits`); a main branch whose check failed after a merge; a red run of a scheduled workflow
(`watched`); and a revert. `watch` names no cause and changes nothing.
`rewritten` tells a launched row's crew once when its brief lost lines it had the pass before.
A finding that no rule covers becomes a gate. `status` gives the table's derived column for a slug.
`why` gives the reason the slug's row waits: the line that `jmerge` has for the slug's pull request,
what stopped the slug's launch, or what the slug's Result leaves.

A pull request belongs to the slug whose brief names it on the `Branch:` line of a Result,
and `jmerge` ties the two the same way (`tied`). The name of a pull request's branch gives
its slug only where no brief names the pull request.

`work.judge` judges a row's state once a pass, from the row's `facts`. The facts of a thread out
that belongs to no row are `thread_facts`. A row's status, one of `queue.STATUSES`, is the
projection of the row's state (`work.status`): `gate`, `pr`, `merged`, `done`, `left`, `launched`,
`running`, `waiting`, `stale`, `failed` or `queued`. For a row that merged, ended or left
something, the row's `why` is what its Result leaves. A row is stale when its thread ended or hung
and wrote nothing, but for a thread whose turn ended on a wait that jbus owns: such a row is
running, since jbus wakes its thread (`World.awaits`). Until `UNWRITTEN_MINUTES` after the thread
last wrote, jbus keeps resuming the row's crew. After that, the row is `left` (`unwritten`), its
`why` says so, and the slug's home closes the row (`leftover`).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import below, findings
from jbriefs import home as homes
from jbriefs.home import thread_of
from jbus import (
    Refused,
    budget,
    budgethold,
    history,
    queue,
    read_json,
    review,
    shots,
    t3,
    verbs,
    work,
    write_json,
)
from jbus.judged import Said, parse
from jbus.launches import records
from jbus.mirror import last_result, sections
from jbus.passes import Changed, Depends, Pass, Red, Rerun, Slot, side_by_side
from jbus.t3 import Client, T3Error
from jbus.wake import cut
from jgauge import holders, slot, waiters
from jmerge import checks as reading
from jmerge import judgement, mainjson
from jmerge import stacked as stacks
from jmerge.asked import Silent
from jmerge.asked import why as asked_why
from jmerge.checks import NOT_RED
from jmerge.joblog import Failed, failed_in, plain
from jsettings import budget as allowance
from jsettings import paths

EVENTS = {"merged": "quiet", "stale": "quiet", "retro": "quiet"}
TITLE = "crew: "
STARTING = ("preparing", "queued", "starting")
LIVE = (*STARTING, "running", "waiting")
ENDED = ("failed", "interrupted", "cancelled")
KNOWN = (*LIVE, *ENDED, "completed")
TIMEBOX_HOURS = 4.0
WAITING_MINUTES = 30
UNWRITTEN_MINUTES = 15
RETRO = timedelta(hours=24)
NO_JOB = "nojob"
"""What `_check` answers for a commit on main whose failed check runs started no job."""
BATCHED = "batched"
"""What `_check` answers for a commit under main's tip whose push run GitHub cancelled before it
had a job: a newer push displaced it from check.yml's group `check-main`, and the next run that
ran checks its merge with the rest of its range (`scripts/green_tree.py --last-checked`)."""
RERUNS = "reruns.json"
"""The push runs on main whose failed jobs jbus asked GitHub to rerun, by id: when it asked,
and whether GitHub took the rerun."""
FAILS = "fails.json"
"""The heads at which each row's pull request failed a required check, kept by `jbus.stall.twice`,
and whether jbus held the row for it."""
TWICE = "check failed twice"
RERUN_WAIT = timedelta(minutes=30)
"""How long `_check` waits for GitHub to show the rerun it took before the run is failed."""
NIGHTLY_RED = ("failure", "timed_out")
NIGHTLY_WINDOW = timedelta(days=3)
NIGHTLY_GRACE = timedelta(hours=1)
GREEN = "passed"
"""What a nightly's `seen` keeps for a run of it that passed on its `branch`."""
_TIMEBOX = re.compile(r"^TIMEBOX:\s*(\d+(?:\.\d+)?)\s*(?:h\b|hours?\b)", re.M)
OPEN = "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,updatedAt"
JOBS, KEPT_JOBS = "completed-jobs.json", 1000
"""The file of the project's state where `ran` keeps completed jobs, and how many it keeps."""
NEVER = "neverStarted"
"""The key of an open pull request's failed checks whose job ran no step, as the pass found
them: `checks` reads them as `jmerge --checks` does. `look` works it out only for a pull request
of a queue row or of a crew jbus launched, the only ones whose readers (`cancelled.rerun`,
`rebase.ran_and_failed`) use it; for any other, `checks` gives the same word without it."""
MERGED = "number,url,title,headRefName,headRefOid,baseRefName,mergeCommit,mergedAt"
GATED = "a gate the Chef has"
OFF, STOP, UNREAD = "dispatch is off", "the stop file is there", "not read in this pass"
AFTER_MERGE = "after the merge"
UNRESOLVED = "Could not resolve to a"
WORDS = 100
_PULL = re.compile(r"^(https?://\S+/pull/(\d+))/?$")
_AGAINST = re.compile(r"^Pull request:[ \t]*open one against (?P<branch>[^\s,;:()`]+)", re.M)


def owned_waits(locks: Path) -> set[str]:
    """The threads whose turn ended on a wait that jbus owns and ends with a wake (`slotwait`):
    one waits on a test slot and is not woken yet (`jgauge.waiters`), or its own run holds a test
    slot now, or ended with its wake not yet sent (`jgauge.holders`). The one rule for such a
    wait, which `World.awaits` and the `Stop` hook (`jbus.crewend`) read."""
    return {one.thread for one in waiters.read(locks) if not one.woken} | {
        one.thread for one in holders.read(locks) if one.ended or holders.running(one)
    }


@dataclass
class World:
    """A `World` is one pass's answers. `threads` holds a slug's threads that are not settled.

    T3 Code's list leaves out an archived thread, so `jbus.archived` asks after each launched
    thread that the list does not have. `archived` holds, by slug, the threads that T3 Code
    reports as archived. `missing` holds the slugs whose thread is unknown to T3 Code, and
    `unasked` the slugs for which jbus could not ask T3 Code. `awaiting` holds the threads whose
    turn ended on a wait that jbus owns (`owned_waits`), which jbus reads once a pass.

    `results` holds each row's last Result as `look` read it, after T3 Code's list and before
    GitHub's, so a pass judges one world. A crew opens its pull request and then writes the Result
    that names it, so a Result in `results` names no pull request GitHub's lists could miss, and a
    thread T3 Code listed as ended wrote its Result before `look` read it.

    `logs` holds each job's log that a step of the pass read, by the job's id, or None where GitHub
    did not give it, so that `watch`, `rebase` and `cancelled` read a failed job's log once a pass
    (`job_log`). `jobs` holds what `ran` keeps of completed jobs, read from `JOBS` once a pass.
    """

    threads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    settled: dict[str, dict[str, Any]] = field(default_factory=dict)
    archived: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)
    unasked: set[str] = field(default_factory=set)
    open: dict[str, dict[str, Any]] = field(default_factory=dict)
    merged: dict[str, dict[str, Any]] = field(default_factory=dict)
    awaiting: set[str] = field(default_factory=set)
    results: dict[str, str] = field(default_factory=dict)
    logs: dict[str, str | None] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] | None = None

    def thread(self, slug: str) -> dict[str, Any] | None:
        live = self.threads.get(slug, [])
        if live:
            return live[0] if len(live) == 1 else None
        return self.settled.get(slug) or self.archived.get(slug)

    def awaits(self, thread: dict[str, Any] | None) -> bool:
        """Say whether the thread's turn ended on a wait that jbus owns, so that jbus wakes it: it
        waits on a test slot, or its own run holds one (`slotwait`). A review or a check of its
        pull request is such a wait too, and the row is `pr` while it lasts."""
        at = jsettings.thread_id(str((thread or {}).get("threadId", "")))
        return bool(at) and at in self.awaiting

    def result(self, run: Pass, slug: str) -> str:
        """The slug's last Result as `look` read it, or as the brief has it now for a slug that
        is no row's."""
        if slug in self.results:
            return self.results[slug]
        return last_result(brief_of(run, slug))

    def live(self) -> tuple[str, ...]:
        """The slug of each crew thread at work, once for each such thread."""
        return tuple(slug for slug, found in self.threads.items() for t in found if at_work([t]))

    def stack_on(self, run: Pass, unmet: list[str], brief: str) -> stacks.Stacked | None:
        """The open pull request a row whose depends `unmet` are not over launches stacked on: the
        one row it still waits on, once that row's pull request is open. A stack sits on one
        branch, so a row that waits on two or more rows launches on none, and nor does a row
        whose `brief` goes on another branch than that row's (`against`): it waits for that row
        to merge."""
        if len(unmet) != 1 or unmet[0] not in self.open:
            return None
        if against(queue.brief(run.state, unmet[0]) or "") != against(brief):
            return None
        branch = str(self.open[unmet[0]].get("headRefName") or "")
        return stacks.Stacked(unmet[0], branch) if branch else None


@dataclass(frozen=True)
class Waits:
    """A `Waits` is what `jmerge` said of waiting pull requests, by number: `wait: <its reason>`.

    `failed` means `jmerge` did not run to its end here, so the pass knows nothing of a
    number that `said` does not have.
    """

    said: dict[str, str]
    failed: bool = False


@dataclass
class Look:
    """A `Look` holds what a pass could learn. `world` is set when T3 Code and GitHub both
    answered.

    `out` is the slug of each crew thread that T3 Code lists as live, once for each thread, which
    jbus knows whenever T3 Code answered. A pass counts them by home and by project
    (`dispatch.Caps`). `why` is the reason T3 Code did not answer. `held` is why the pass asked
    GitHub nothing to save its API budget, or why it could not tell what is left of it.
    `spent` is the line that says GitHub's API allowance is spent: a window with no call left,
    or a call GitHub refused for its rate limit (`jsettings.budget`). It is empty where neither,
    and None where the pass could not tell, since GitHub did not say what is left. `left` is
    what the pass read of the budget, or None where GitHub did not say.
    """

    world: World | None = None
    out: tuple[str, ...] | None = None
    why: str = ""
    held: str = ""
    spent: str | None = None
    left: budget.Budget | None = None


def when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def at_work(
    threads: Iterable[dict[str, Any]], title: str | None = None, *, settled_too: bool = False
) -> bool:
    """Say whether any of the threads is at work: its status is one of `LIVE` and it is not
    settled. With a `title`, `TITLE` and a slug, only the slug's own thread counts. A caller that
    sent a settled thread a message counts it too (`settled_too`), since T3 Code leaves a thread
    settled while it takes up a message."""
    return any(
        thread.get("status") in LIVE
        and (settled_too or not thread.get("settled"))
        and (title is None or TITLE + thread["title"].removeprefix(TITLE).strip() == title)
        for thread in threads
    )


def crew_threads(client: Client, project_id: str, contains: str = TITLE) -> list[dict[str, Any]]:
    found = t3.listed(client, project_id, titleContains=contains)
    return [t for t in found if str(t.get("title", "")).startswith(TITLE)]


def _silent(run: Pass, why: str) -> Look:
    """Record once a day that T3 Code gave no answer. The pass then launches nothing and watches
    nothing."""
    name = run.project.name
    run.say(f"wait {name}: T3 Code could not be asked ({why})")
    day = run.now.date().isoformat()
    run.condition(name, "T3 Code could not be asked", why, key=f"t3 {day}")
    return Look(why=why)


def pulls(run: Pass, state: str, fields: str, *more: str) -> list[dict[str, Any]]:
    """Return the pull requests that `gh` lists, or raise `Silent` if `gh` gave none."""
    asked = run.run("gh", "pr", "list", "--state", state, "--json", fields, *more)
    try:
        pulls = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        pulls = None
    if not isinstance(pulls, list):
        raise Silent(asked_why(asked, run.run))
    return pulls


def _named(run: Pass, url: str) -> list[dict[str, Any]]:
    """Return the pull request at this address if it merged, as a list like the one `pulls`
    returns.

    If GitHub says it cannot resolve the address, `_named` returns no pull request and the
    pass goes on, since a brief may name such an address. If `gh` failed any other way, it
    gave no answer, and `_named` raises `Silent`.
    """
    asked = run.run("gh", "pr", "view", url, "--json", f"{MERGED},state")
    if asked.returncode and UNRESOLVED in asked.stderr:
        return []
    try:
        pull = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        pull = None
    if not isinstance(pull, dict):
        raise Silent(asked_why(asked, run.run))
    return [pull] if pull.get("state") == "MERGED" else []


def named(result: str) -> tuple[str, str]:
    """Return the address and number of the pull request at the end of a Result's `Branch:`
    line."""
    words = below.line(result, "Branch:").split()
    found = _PULL.match(words[-1]) if words else None
    return (found[1], found[2]) if found else ("", "")


def tied(run: Pass) -> dict[str, str]:
    """Return the slug of each pull request that a brief names, by its address.

    A brief names a pull request with a `Branch:` line that ends on its address, in any of
    its Results. The first brief with such a line gives the slug, as it does for `jmerge`.
    """
    found: dict[str, str] = {}
    for path in sorted((run.home / "tasks").glob("*.md")):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            url = named(line)[0] if line.startswith("Branch:") else ""
            if url:
                found.setdefault(url, path.stem)
    return found


UNMERGED = "unmerged.json"
UNMERGED_FOR = timedelta(hours=6)


class Missed:
    """The slugs that `look` asked GitHub for by name and found no merge for, kept in
    `UNMERGED`, so a pass does not ask again for each row that never merged.

    A slug's pull request merges after it was open, and a pass sees every open pull request
    (the open list) and the last hundred merged, so a slug seen open is asked again once it is
    gone from both. A slug's answer is kept for `UNMERGED_FOR`, and only for what was asked: its
    branch, or the address its brief names (`by`), so a brief that names a new address is asked
    again at once.
    """

    def __init__(self, run: Pass, world: World) -> None:
        self.path, self.now = run.state / UNMERGED, run.now
        self.was: dict[str, dict[str, str]] = read_json(self.path, {})
        self.known = {
            slug: one
            for slug, one in self.was.items()
            if slug not in world.open and self.now - when(one["at"]) < UNMERGED_FOR
        }

    def knows(self, slug: str, by: str) -> bool:
        one = self.known.get(slug)
        return one is not None and one["by"] == by

    def add(self, slug: str, by: str) -> None:
        self.known[slug] = {"by": by, "at": self.now.isoformat()}

    def keep(self) -> None:
        if self.known != self.was:
            write_json(self.path, self.known)


BASES = "bases.json"
"""The tips of the project's base branches when `look` last read the list of merged pull
requests, by branch, kept in the project's state."""


def base_tips(run: Pass) -> dict[str, str] | None:
    """Return the tip of each of the project's base branches (the default branch and its
    `merge_bases`) by name, from one `git ls-remote origin`, or None where git gave no answer."""
    bases = sorted({_default_branch(run), *run.project.merge_bases})
    asked = run.run("git", "ls-remote", "origin", *(f"refs/heads/{base}" for base in bases))
    if asked.returncode != 0:
        return None
    tips = {}
    for line in asked.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.removeprefix("refs/heads/") in bases:
            tips[ref.removeprefix("refs/heads/")] = sha
    return tips


def _newest(kept: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the hundred newest merges `merged.json` keeps, each once, as GitHub's list of merged
    pull requests gives them."""
    by_url = {pull.get("url", "").rstrip("/") or slug: pull for slug, pull in kept.items()}
    return sorted(by_url.values(), key=lambda p: p.get("mergedAt") or "", reverse=True)[:100]


def look(run: Pass, client: Client | None, rows: list[dict[str, Any]]) -> Look:
    """Ask T3 Code and GitHub. If either one is silent, there is no world to act on.

    When GitHub is silent, jbus still knows the crews out, and they count toward `max_running`.

    The list of merged pull requests is the last hundred. `look` keeps every merge it sees in
    `merged.json` of the project's state, a record of the merges written on each one. When the
    queue names a slug that is in neither, `look` asks GitHub for it by name, and keeps the merge
    it finds that way too, so the slug stays merged. It keeps a slug it found no merge for too
    (`Missed`), and does not ask for it again on each pass.

    A merge moves its base branch, so `look` asks for the merged list only when a base branch
    moved since it last did (`base_tips`, kept in `BASES`), or git gave no tips. Otherwise the
    hundred newest merges of `merged.json` stand in for the list. Until a base moves, such a pass
    misses a merge into a branch that is no base, and a merged pull request's later edit.

    `look` keeps a pull request under the slug whose brief names it (`tied`), and under the
    name of its branch where no brief does. When a slug's brief names a pull request, `look`
    asks for that pull request by its address.

    First of all, `look` reads GitHub's API budget (`jbus.budget`), from what the calls of the
    last minute logged (`allowance.logged`), so that the projects of a pass ask `gh api
    rate_limit` once between them at most. Every `Look` it returns holds it, T3 Code silent or
    not: a step that spends the budget needs it. With no answer, or
    with the budget at or under its floor, `look` asks GitHub nothing else, and the pass has no
    world, as when GitHub is silent: no row changes. `jmerge` ran before, so a merge still goes.
    """
    asked: list[subprocess.CompletedProcess[str]] = []

    def ask(command: list[str]) -> str | None:
        asked.append(run.run(*command))
        return asked[-1].stdout if asked[-1].returncode == 0 else None

    left = allowance.logged(paths.jbus_state_dir(), asked=ask)
    held = budget.held(left)
    spent = None if left is None else allowance.spent(left)
    if client is None:
        return replace(
            _silent(run, "no token: run `jbus t3 login`"), held=held, spent=spent, left=left
        )
    locks = slot.locks_dir()
    world = World(awaiting=owned_waits(locks))
    try:
        listed = crew_threads(client, run.project.project_id)
    except T3Error as error:
        return replace(_silent(run, str(error)), held=held, spent=spent, left=left)
    slug_of = tied(run)
    url_of = {slug: url for url, slug in slug_of.items()}
    world.results = {row["slug"]: last_result(brief_of(run, row["slug"])) for row in rows}
    for thread in sorted(listed, key=lambda t: t.get("createdAt", "")):
        slug = thread["title"][len(TITLE) :].strip()
        if thread.get("settled"):
            world.settled[slug] = thread
        else:
            world.threads.setdefault(slug, []).append(thread)
    out = world.live()
    for slug in run.removed:
        world.threads.pop(slug, None)
    if left is None:
        why = asked_why(asked[-1], run.run) if asked else f": {held}"
        run.say(f"wait {run.project.name}: could not ask GitHub{why}")
        return Look(out=out, held=held)
    if held:
        run.say(f"wait {run.project.name}: GitHub not asked: {held}")
        key = f"budget {left.low.name} {left.low.reset.isoformat()}"
        run.condition(run.project.name, "GitHub's API budget is under the floor", held, key=key)
        return Look(out=out, held=held, spent=spent, left=left)
    kept: dict[str, dict[str, Any]] = read_json(run.state / "merged.json", {})
    named = {slug for row in rows for slug in (row["slug"], *row.get("depends", []))}
    queued = {row["slug"] for row in rows}
    tips = base_tips(run)
    unmoved = tips is not None and read_json(run.state / BASES, None) == tips
    try:
        for pull in pulls(run, "open", OPEN, "--limit", "100"):
            slug = slug_of.get(pull.get("url", "").rstrip("/"), pull["headRefName"])
            if slug in queued or records(run, slug, queue.CREW):
                rollup = pull.get("statusCheckRollup") or []
                pull[NEVER] = sorted(
                    reading.never_started(rollup, lambda *at: ran(run, world, *at))
                )
            world.open[slug] = pull
        merges = _newest(kept) if unmoved else pulls(run, "merged", MERGED, "--limit", "100")
        for pull in sorted(merges, key=lambda p: p.get("mergedAt") or ""):
            world.merged[slug_of.get(pull.get("url", "").rstrip("/"), pull["headRefName"])] = pull
        if kept | world.merged != kept:
            kept |= world.merged
            write_json(run.state / "merged.json", kept)
        if tips is not None and not unmoved:
            write_json(run.state / BASES, tips)
        missed = Missed(run, world)
        for slug in sorted(named - set(world.open) - set(world.merged)):
            if slug not in kept:
                by = url_of.get(slug, "")
                if missed.knows(slug, by):
                    continue
                if by:
                    found = _named(run, by)
                else:
                    found = pulls(run, "merged", MERGED, "--head", slug, "--limit", "1")
                if not found:
                    missed.add(slug, by)
                    continue
                kept[slug] = found[0]
                write_json(run.state / "merged.json", kept)
            world.merged[slug] = kept[slug]
        missed.keep()
    except Silent as silent:
        run.say(f"wait {run.project.name}: could not ask GitHub{silent}")
        said = str(silent).removeprefix(": ")
        return Look(out=out, spent=said if allowance.is_named(said) else spent, left=left)
    return Look(world, out, spent=spent, left=left)


def checks(pull: dict[str, Any]) -> str:
    """Return a pull request's checks in one word, as `jmerge --checks` reads them
    (`jmerge.checks`), counting the failed checks that the pass found whose job ran no step
    (`NEVER`). A check that never started, beside checks that passed, gives `failed`, the
    first word that `jmerge --checks` prints for such a check. `jmerge` decides a merge, not
    `checks`."""
    rollup, never = pull.get("statusCheckRollup") or [], frozenset(pull.get(NEVER) or ())
    word = reading.checks(rollup, never)
    return "failed" if word == "unstarted" else word


def ran(run: Pass, world: World, repo: str, number: str) -> dict:
    """Return what `never_started`, `rebase.ran_and_failed` and `jbus.stall.infra` read of a job:
    `steps`, which is `[]` where the job ran no step, `run_attempt`, and `failed_step`, the name of
    its first step that failed (`collect.failed_step`), or nothing. A completed job's steps and
    attempt never change (a rerun is a new job id), so `ran` keeps them by repo and job id in the
    project's `JOBS`, the last `KEPT_JOBS` of them, and asks GitHub for a job id it keeps no more.
    A job kept before `failed_step` was gives none. A job that is not completed is not kept, and
    is given as GitHub gives it, or {}, with its `failed_step`."""
    from jbus.ci.collect import failed_step

    if world.jobs is None:
        world.jobs = read_json(run.state / JOBS, {})
    key = f"{repo}/{number}"
    kept = world.jobs.get(key)
    if kept is None:
        given = job(run, repo, number)
        if given.get("status") != "completed":
            return {**given, "failed_step": failed_step(given) or ""}
        kept = {
            "steps_empty": given.get("steps") == [],
            "run_attempt": given.get("run_attempt"),
            "failed_step": failed_step(given) or "",
        }
        world.jobs[key] = kept
        world.jobs = dict(list(world.jobs.items())[-KEPT_JOBS:])
        write_json(run.state / JOBS, world.jobs)
    return {
        "steps": [] if kept["steps_empty"] else None,
        "run_attempt": kept["run_attempt"],
        "failed_step": kept.get("failed_step", ""),
    }


def job(run: Pass, repo: str, number: str) -> dict:
    """Return a job of a workflow run as GitHub gives it, or {} where GitHub gives none."""
    asked = run.run("gh", "api", f"repos/{repo}/actions/jobs/{number}")
    try:
        given = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        given = {}
    return given if isinstance(given, dict) else {}


def task_brief(run: Pass, slug: str) -> str:
    """Return the slug's brief under the home's `tasks/`, or nothing where there is none."""
    try:
        return (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        return ""


def brief_of(run: Pass, slug: str) -> str:
    """Return the slug's brief under the home's `tasks/`, else its queued brief, or nothing. A
    brief this pass read before is served from `run.briefs` while its mtime and size are those
    it had then, so a brief written since is read again."""
    for path in (run.home / "tasks" / f"{slug}.md", run.state / "briefs" / f"{slug}.md"):
        try:
            seen = path.stat()
            key = (seen.st_mtime_ns, seen.st_size)
            kept = run.briefs.get(path)
            if kept and kept[0] == key:
                return kept[1]
            text = path.read_text(errors="replace")
        except OSError:
            continue
        run.briefs[path] = (key, text)
        return text
    return ""


def _stale(run: Pass, world: World, slug: str, thread: dict[str, Any]) -> str:
    status, text = thread["status"], brief_of(run, slug)
    if status == "running":
        limit = _TIMEBOX.search(text)
        hours = (run.now - when(thread["createdAt"])).total_seconds() / 3600
        if hours > (float(limit[1]) if limit else TIMEBOX_HOURS):
            return f"stale {slug}: running {int(hours)}h, past its TIMEBOX"
    elif status == "waiting":
        minutes = (run.now - when(thread["updatedAt"])).total_seconds() / 60
        if minutes >= WAITING_MINUTES:
            return f"stale {slug}: waiting on a request {int(minutes)} min"
    elif status in (*ENDED, "completed") and not world.result(run, slug):
        if not world.awaits(thread):
            return f"stale {slug}: thread {status} with no Result"
    return ""


def left(result: str) -> str:
    """Return, in a few words, what a Result leaves undone. Return nothing when the Result says
    `Status: done` and `Left: none`."""
    status, rest = below.line(result, "Status:"), below.line(result, "Left:")
    if rest and rest != "none":
        return f"left: {cut(rest, WORDS)}"
    if status != "done":
        return f"status: {cut(status, WORDS)}" if status else "its Result has no Status line"
    return "" if rest else "its Result has no Left line"


def unfinished(result: str) -> str:
    """Return what keeps a Result with no merge from ending its task, or nothing.

    The answer is what the Result leaves, or a `Branch:` line that is missing or that ends on
    an address. An address there means a pull request that is neither open nor merged. This
    function is the one rule for a task that ended with no pull request: `ended` and
    `threads.finished` both call it.
    """
    short, words = left(result), below.line(result, "Branch:").split()
    if short:
        return short
    if not words:
        return "its Result has no Branch line"
    if words[-1].startswith("http"):
        number = named(result)[1]
        return f"pull request{f' #{number}' if number else ''} is not open and not merged"
    return ""


def owes_pull(run: Pass, slug: str, brief: str, result: str) -> bool:
    """Say whether a crew's Result that would end its task clean still owes the pull request its
    brief asks for (`Pull request: open one ...`): its `Branch:` line names none, and that branch
    has a commit of its own (`own`). Such a task is not done, whatever its `Status:` says: its row
    runs, and its thread is told once to open it (`threads.resume`).

    A Result that says its pull request opens after its review (`review.before_pull`) owes it
    whatever the brief's header says, when the brief asks for a review: the crew waits on that
    review (`jbus.prereview`). While the review is due, running, or refused and told to the crew
    (`review.awaited`), a Result with `Status: done` owes it whatever its `Left:` line names,
    since that work rides along to after the merge and does not end the row. A follow-up Result
    that says so owes it as the first did, before the review and after it: the crew's answer to a
    review jbus refused, or a correction of a line of its Result. Once the review ran, a Result
    that leaves something is the home's to close if its crew opens nothing (`leftover.opening`).
    Otherwise a crew that found nothing to change owes nothing. Nor does a brief whose
    `Pull request:` line says none, a scout's or a report's, or any other follow-up Result, a later
    round: the home's close of a row nothing more is wanted of (`leftover`), or the crew's answer
    once it was told. The rule is judged as a row moves to done: a row the table had at done when
    the pass began owes nothing (`Pass.done`)."""
    after = review.before_pull(result) and findings.mode_of(brief) != findings.NONE
    awaits = below.line(result, "Status:") == "done" and review.awaited(brief, result)
    later = not result.startswith("## Result\n") and not after
    if not awaits and (later or unfinished(result)):
        return False
    if slug in run.done:
        return False
    if awaits or after:
        return True
    if history.pull(brief) != "open":
        return False
    return own(run, below.line(result, "Branch:").split()[0])


def own(run: Pass, branch: str) -> bool:
    """Say whether a branch has a commit on neither the default branch nor the commit it was made
    from, the first line of its reflog: a crew's worktree starts from main, or from the branch of
    the link it was stacked on, whose commits are not the crew's. A branch that is gone has none."""
    ref = f"refs/heads/{branch}"
    made = run.run("git", "reflog", "show", "--format=%H %gs", ref).stdout.splitlines()
    start = made[-1].split()[0] if made and " branch: Created from " in made[-1] else ""
    base = f"origin/{_default_branch(run)}"
    asked = run.run("git", "rev-list", "-n", "1", ref, "--not", base, *filter(None, [start]))
    return not asked.returncode and bool(asked.stdout.strip())


def after_merge(result: str) -> bool:
    """Return whether a Result leaves work for after its merge. The pass tells the thread
    about that work."""
    return below.line(result, "Left:").lower().startswith(AFTER_MERGE)


@dataclass(frozen=True)
class End:
    """An `End` is the outcome of a row whose thread ended with a Result: `done`, or `left`
    with a `why`."""

    word: str
    why: str = ""


def ended(run: Pass, world: World, slug: str) -> End | None:
    """Return the end of a slug whose thread ended with a Result and no pull request pending.

    The slug's thread has ended when the thread is settled or no longer `LIVE`. If T3 Code lists no
    thread for a slug, the slug has not started, or this pass launched it. A slug with a pull
    request that is open or merged takes its status from that pull request. A Result that still
    owes its pull request (`owes_pull`) has not ended the slug.
    """
    thread = world.thread(slug)
    if slug in world.open or slug in world.merged:
        return None
    if thread is None or at_work([thread]):
        return None
    result = world.result(run, slug)
    if not result or owes_pull(run, slug, brief_of(run, slug), result):
        return None
    short = unfinished(result)
    return End("left", short) if short else End("done")


def gone(run: Pass, world: World, slug: str, launched: str) -> bool:
    """Return whether a slug's thread is gone and wrote nothing. The answer is yes when four
    things hold: jbus launched the slug; T3 Code lists no thread for the slug, not even a
    settled or archived one; no pull request of the slug is open or merged; and the slug's
    brief has no Result.

    `launched` is the thread of the slug's launch record, or nothing for a slug with none. A
    pass calls `gone` before it launches anything, with the answers that it already has from
    T3 Code and GitHub. A thread launched after jbus got those answers appears in neither.
    """
    if not launched or slug in world.threads or slug in world.settled or slug in world.archived:
        return False
    return (
        slug not in world.open and slug not in world.merged and not last_result(brief_of(run, slug))
    )


def written(result: str) -> work.Written:
    """Return what a Result says, as the facet `Written` has it: nothing, `clean` where it
    leaves nothing and has a `Branch:` line, `leftover` where its `Left:` line names something
    or its `Status:` is not `done`, and `malformed` where one of the three lines is missing."""
    if not result:
        return work.Written.NONE
    short = left(result)
    if short.startswith(("left: ", "status: ")):
        return work.Written.LEFTOVER
    if short or not below.line(result, "Branch:").split():
        return work.Written.MALFORMED
    return work.Written.CLEAN


def pull(world: World, slug: str, result: str, said: str) -> work.Pull:
    """Return the slug's pull request as the facet `Pull` has it. `said` is what `jmerge`
    last said of an open one (`jmerge.judgement.step`). A `Branch:` line that ends on an address,
    with neither an open nor a merged pull request under the slug, means that pull request
    closed."""
    if slug in world.open:
        return work.Pull(judgement.step(said) or work.Pull.OTHER)
    if slug in world.merged:
        return work.Pull.MERGED
    words = below.line(result, "Branch:").split()
    return work.Pull.CLOSED if words and words[-1].startswith("http") else work.Pull.NONE


def thread(found: dict[str, Any] | None, live: str) -> work.Thread | None:
    """Return a thread as the facet `Thread` has it, from its status and its liveness
    (`jbus.live`). A turn whose liveness is not known is `quiet`, and jbus never calls it
    moving. A status jbus does not know gives no facet at all: None."""
    if found is None:
        return work.Thread.NONE
    if found.get("archived"):
        return work.Thread.ARCHIVED
    if found.get("settled"):
        return work.Thread.SETTLED
    status = found.get("status", "")
    if status in STARTING:
        return work.Thread.STARTING
    if status == "waiting":
        return work.Thread.WAITING
    if status == "running":
        return LIVENESS.get(live, work.Thread.QUIET)
    if status in ("completed", "idle"):
        return work.Thread.COMPLETED
    return work.Thread.FAILED if status in (*ENDED, "rolled_back") else None


LIVENESS = {
    "moving": work.Thread.MOVING,
    "quiet": work.Thread.QUIET,
    "hung": work.Thread.HUNG,
    "waiting": work.Thread.WAITING,
}


@dataclass(frozen=True)
class Seen:
    """A `Seen` is what a pass saw besides the world: the threads out (`threads.out`), or None
    where T3 Code did not list them; the slugs whose launched thread is gone with nothing
    written (`gone`); what `jmerge` said of each open pull request by its number; the slugs
    that are merged or done (`final`); and which sources answered."""

    out: list[dict[str, Any]] | None
    gone: frozenset[str]
    said: dict[str, str]
    final: frozenset[str]
    answered: work.Answered = work.Answered.BOTH

    def live(self, thread: str) -> str:
        return next((one["live"] for one in self.out or [] if one["id"] == thread), "")

    def crew(self, slug: str) -> dict[str, Any] | None:
        """Return the one crew thread out for a slug, as it appears in the list of threads out."""
        return self.one_out("crew", slug)

    def one_out(self, role: str, slug: str) -> dict[str, Any] | None:
        """Return the one thread of `role` out for a slug, as the list of threads out has it."""
        found = [one for one in self.out or [] if one["role"] == role and one["slug"] == slug]
        return found[0] if len(found) == 1 else None


def against(brief: str) -> str:
    """The branch a brief's `Pull request:` line opens its pull request against, or empty for the
    default branch."""
    named = _AGAINST.search(brief.split("\n## ", 1)[0])
    return named["branch"] if named else ""


def unmet(run: Pass, world: World | None, row: dict[str, Any], final: frozenset[str]) -> list[str]:
    """The depends that hold back a row's launch: none for a row that launches stacked on the one
    it waits on (`World.stack_on`)."""
    left = [one for one in row.get("depends", []) if one not in final]
    brief = queue.brief(run.state, row["slug"]) or ""
    return [] if world is not None and world.stack_on(run, left, brief) else left


def final(run: Pass, world: World | None, rows: list[dict[str, Any]]) -> frozenset[str]:
    """Return the slugs that no longer hold back a row that depends on them. Those are the
    slugs that merged, or that ended `done` under the rule that `dispatch` uses to launch.
    With no world, jbus takes them from the rows' own status."""
    if world is None:
        return frozenset(row["slug"] for row in rows if row.get("status") in queue.FINAL)
    merged = set(world.merged) - set(world.open)
    crew = [row for row in rows if queue.role(row) == queue.CREW]
    done = {row["slug"] for row in crew if ended(run, world, row["slug"]) == End("done")}
    return frozenset(merged | done | reported(run, rows))


def reported(run: Pass, rows: list[dict[str, Any]]) -> frozenset[str]:
    """Return the slugs of the scouts' rows whose last Report says `Status: done` (`owed`)."""
    return frozenset(
        row["slug"]
        for row in rows
        if queue.role(row) == queue.SCOUT and owed(run, "scout", row["slug"]) == work.Written.CLEAN
    )


def facts(
    run: Pass, world: World | None, row: dict[str, Any], seen: Seen, launched: str, last: str = ""
) -> tuple[work.Facts, bool]:
    """Return the facts of one row of the queue, and whether its thread is in a status jbus
    does not know. The row's launch record names the thread `launched`, or none. With no
    world, the thread is the one in the list of threads out, and jbus does not know what
    GitHub would say: its facet is `none`, and `judge` passes over every pattern that
    narrows it. A thread whose turn ended on a wait that jbus owns (`World.awaits`) is `quiet`,
    since jbus wakes it, so its row is running and nobody is told it ended. So is one whose Result
    still owes its pull request (`owes_pull`), which counts as nothing written: `threads.resume`
    tells it once."""
    slug = row["slug"]
    if queue.role(row) == queue.SCOUT:
        return _scouted(run, world, row, seen, launched, last)
    if world is not None:
        result = world.result(run, slug)
        found = world.thread(slug)
        said = thread(found, seen.live((found or {}).get("threadId", "")))
        if said in OVER and world.awaits(found):
            said = work.Thread.QUIET
    else:
        result = last_result(brief_of(run, slug))
        found = seen.crew(slug)
        said = thread(found, str((found or {}).get("live", "")))
    owes = owes_pull(run, slug, brief_of(run, slug), result)
    if owes and said in OVER:
        said = work.Thread.QUIET
    answered = seen.answered
    if world is not None and found is None and launched:
        if slug in world.missing:
            said = work.Thread.MISSING
        elif slug in world.unasked:
            said, answered = work.Thread.STARTING, work.without_t3(answered)
        elif slug not in seen.gone:
            said = work.Thread.STARTING
    number = str((world.open.get(slug) or {}).get("number", "")) if world else ""
    made = work.Facts(
        row=queue.facet(run.state, row, unmet(run, world, row, seen.final)),
        thread=said or work.Thread.NONE,
        seen="" if said else str((found or {}).get("status", "")),
        launch=work.Launch.LAUNCHED if launched else work.Launch.NONE,
        written=work.Written.NONE if owes else written(result),
        pull=pull(world, slug, result, seen.said.get(number, "")) if world else work.Pull.NONE,
        question=work.Question.OPEN if slug in run.gated else work.Question.NONE,
        answered=answered,
        last=last,
    )
    return made, said is None


def _scouted(
    run: Pass, world: World | None, row: dict[str, Any], seen: Seen, launched: str, last: str
) -> tuple[work.Facts, bool]:
    """Return the facts of a scout's row, as `facts` does for a crewmate's. Its thread is the
    one titled `scout: <slug>` in the list of threads out, and what it wrote is its last Report
    (`owed`). It has no pull request. A launched thread that left the list once its Report was
    written was settled; one that left it with nothing written is still starting, as far as the
    pass can tell. A scout whose turn ended on a wait that jbus owns is `quiet`, as a crew is
    (`facts`): its thread is among the threads out and never `World.thread`, so the wait is looked
    up by the thread's id there."""
    slug = row["slug"]
    one = seen.one_out("scout", slug)
    said = thread(one, str((one or {}).get("live", ""))) if one else None
    if one and said in OVER and world is not None and world.awaits({"threadId": one["id"]}):
        said = work.Thread.QUIET
    written = owed(run, "scout", slug)
    if one is None and launched:
        said = work.Thread.STARTING if written == work.Written.NONE else work.Thread.SETTLED
    made = work.Facts(
        row=queue.facet(run.state, row, unmet(run, world, row, seen.final)),
        thread=said or work.Thread.NONE,
        seen="" if said or one is None else str(one.get("status", "")),
        launch=work.Launch.LAUNCHED if launched else work.Launch.NONE,
        written=written,
        pull=work.Pull.NONE,
        question=work.Question.OPEN if slug in run.gated else work.Question.NONE,
        answered=seen.answered,
        last=last,
    )
    return made, one is not None and said is None


class Judging:
    """A `Judging` holds the state of each row of a pass, judged once, when a caller first
    asks for it. A row added to the queue after the pass read it is judged as the others are.
    A running thread whose liveness the pass could not read, since T3 Code did not list the
    threads out, is `quiet` and not confirmed."""

    def __init__(self, run: Pass, world: World | None, seen: Seen, last: dict[str, str]):
        self.run, self.world, self.seen, self.last = run, world, seen, last
        self.states: dict[str, work.State] = {}

    def of(self, row: dict[str, Any], launched: str) -> work.State:
        slug = row["slug"]
        if slug not in self.states:
            made, strange = facts(
                self.run, self.world, row, self.seen, launched, self.last.get(slug, "")
            )
            asked = made.question == work.Question.OPEN
            state = work.unforeseen(made) if strange and not asked else work.judge(made)
            found = self.world.thread(slug) if self.world is not None else None
            if self.seen.out is None and (found or {}).get("status") == "running":
                state = replace(state, confirmed=False)
            self.states[slug] = state
        return self.states[slug]


OVER = (work.Thread.COMPLETED, work.Thread.FAILED)


def owed(run: Pass, role: str, slug: str) -> work.Written:
    """Return what a thread that belongs to no row has written of the output that its role
    owes.
    A scout owes its last Report, a follow-up (`## Report, follow-up (…)`) as much as the
    first, which jbus reads as it reads a Result. A reviewer owes a
    Review with a verdict in the brief. A home or any other thread owes nothing, so it has
    always written all it owes."""
    if role == "scout":
        text = _read(run.home / "scouts" / f"{slug}.md")
        reports = [body for head, body in sections(text) if head.startswith("## Report")]
        if not reports:
            return work.Written.NONE
        status = below.line(reports[-1], "Status:")
        if not status:
            return work.Written.MALFORMED
        return work.Written.CLEAN if status == "done" else work.Written.LEFTOVER
    if role == "reviewer":
        text = _read(run.home / "tasks" / f"{slug}.md")
        verdicts = [
            below.line(body, "Verdict:") for head, body in sections(text) if head == "## Review"
        ]
        return work.Written.CLEAN if any(verdicts) else work.Written.NONE
    if role == "crew":
        brief = brief_of(run, slug)
        result = last_result(brief)
        return work.Written.NONE if owes_pull(run, slug, brief, result) else written(result)
    return work.Written.CLEAN


def _read(path: Any) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def thread_facts(run: Pass, one: dict[str, Any], answered: work.Answered, last: str) -> work.Facts:
    """Return the facts of a thread out that belongs to no row, one of `threads.out`. The
    thread counts as its own launch. What it wrote counts once its turn is over, since a turn
    under way still writes."""
    said = thread(one, str(one.get("live", "")))
    slug = str(one.get("slug") or "")
    return work.Facts(
        row=work.Row.REMOVED if slug and slug in run.removed else work.Row.ABSENT,
        thread=said or work.Thread.NONE,
        seen="" if said else str(one.get("status", "")),
        launch=work.Launch.LAUNCHED,
        written=owed(run, str(one.get("role", "")), slug) if said in OVER else work.Written.NONE,
        pull=work.Pull.NONE,
        question=work.Question.NONE,
        answered=answered,
        last=last,
    )


def judged(
    run: Pass, out: list[dict[str, Any]] | None, rows: set[tuple[str, str]], answered: work.Answered
) -> list[dict[str, Any]]:
    """Return the `work.json` lines of every thread out that belongs to no row: a reviewer, a
    home, another, and a crew or a scout whose slug has no row of its role. `rows` holds each
    row's role and slug (`queue.role`). With no list of them, return the last pass's lines, not
    confirmed."""
    kept = work.read(run.state) or {"work": []}
    if out is None:
        return [
            {**one, "confirmed": False}
            for one in kept["work"]
            if isinstance(one, dict) and one.get("kind") == "thread"
        ]
    last = work.last(run.state)
    found = []
    for one in out:
        if (one.get("role"), one.get("slug")) in rows:
            continue
        made = thread_facts(run, one, answered, last.get(one["id"], ""))
        state = work.unforeseen(made) if made.seen else work.judge(made)
        role = str(one.get("role") or "other")
        about = {"key": one["id"], "kind": "thread", "slug": one.get("slug") or ""}
        about |= {"thread": one["id"], "role": role, "title": one.get("title", "")}
        found.append(work.entry(state, work.holder(state, role=role), **about))
    return found


def unwritten(run: Pass, world: World, thread: dict[str, Any] | None, state: work.State) -> str:
    """Return why a `stale` row has nobody on it, or nothing while its crew is still on it.

    A thread that ended or hung with nothing written is `stale` for as long as jbus keeps
    resuming the row's crew (`threads.resume`). Once `UNWRITTEN_MINUTES` have passed since the
    thread last wrote, or at once for a hung turn, the row is a leftover, and jbus sends the row
    to the slug's home to close (`leftover`). The row stays `left` until the home ends it, the
    thread goes on, or the row leaves the queue.

    A thread whose turn ended on a wait that jbus owns is never `stale` (`facts`). If its turn
    hung while it waits on a test slot or its own run holds one (`World.awaits`), its row is never
    `left` either, however long the thread is quiet: jbus wakes the thread when a slot is free, or
    when its run ends (`slotwait`). After that, the rule above counts again from the thread's last
    write.
    """
    if state.value not in ("lost", "hung") or state.facts.written != work.Written.NONE:
        return ""
    if world.awaits(thread):
        return ""
    if state.value == "hung":
        return "its turn hung with nothing written"
    if thread is None:
        return "its thread is gone and nothing is written"
    quiet = (run.now - when(thread["updatedAt"])).total_seconds() / 60
    if quiet < UNWRITTEN_MINUTES:
        return ""
    return f"its thread {thread['status']} with nothing written"


def status(
    run: Pass, world: World, slug: str, state: work.State, launched: str = ""
) -> dict[str, str]:
    """Return a row's derived columns. The row's status is the projection of the row's state
    (`work.status`). `why` holds the reason that comes with the status itself: what a Result
    leaves.

    `launched` is the thread id of the slug's launch record.
    """
    found = world.thread(slug)
    pull = world.open.get(slug) or world.merged.get(slug)
    word = work.status(state)
    reason = ""
    if word == "stale" and (why := unwritten(run, world, found, state)):
        word, reason = "left", why
    elif word in ("merged", "left", "done"):
        result = world.result(run, slug)
        reason = (left(result) if word == "merged" else unfinished(result)) if result else ""
    return {
        "thread": (found or {}).get("threadId") or launched,
        "pr": f"#{pull['number']}" if pull else "",
        "checks": checks(pull) if pull is not None and slug in world.open else "",
        "status": word,
        "why": reason,
    }


def waits(pulls: Said) -> Waits:
    """Return what `jmerge` waits for or holds, by the pull request's number.

    `pulls` is what `jmerge` said in this pass (`merge.shown`), also where the home merges.
    """
    found = (parse(line) for line in pulls if isinstance(line, str))
    by_number = {
        str(line.number): f"{line.word}: {line.reason}"
        for line in found
        if line and line.word in ("wait", "hold") and line.reason
    }
    return Waits(by_number, failed=pulls.failed)


def unread(run: Pass, read: bool) -> str:
    """Return why `dispatch` read no row of the queue this pass, or nothing if it `read` them.

    `UNREAD` means the pass did not get to the launches: a project raised, or T3 Code,
    GitHub or the queue gave no answer, so nothing could launch.
    """
    if read:
        return ""
    if not run.config.dispatch:
        return OFF
    return STOP if run.config.stop_path.exists() else UNREAD


def failed_twice(run: Pass, slug: str) -> bool:
    """Say whether jbus held the row because its check failed at two heads (`jbus.stall.twice`)."""
    kept = read_json(run.state / FAILS, {})
    one = kept.get(slug) if isinstance(kept, dict) else None
    return isinstance(one, dict) and bool(one.get("held_at"))


def why(run: Pass, row: dict[str, Any], found: dict[str, str], waits: Waits, unread: str) -> str:
    """Return why a row waits, or nothing. `found` is its derived columns, as `status` gave them.

    A held row whose check failed at two heads waits for `TWICE` (`jbus.stall.twice`). A row with
    a pull request waits for what `jmerge` says of it, after the question this pass asked of it
    (`Pass.asked`) where there is one, as in the pass that holds it for `TWICE`. A row that was not
    launched waits for what `dispatch` recorded (`Pass.reasons`), or for its approval. Where
    `dispatch` read no row, it recorded nothing, and an approved row waits for what is `unread`:
    dispatch that is off, or the stop file. A pass that is `UNREAD` says nothing of the row, so
    the row's stored reason stays, unless the row has got its approval since. The same holds for a
    pass in which `jmerge` failed and printed no line for the pull request. A row that ended, or
    that merged with work left for after it, takes its reason from `status`.
    """
    if found.get("why"):
        return found["why"]
    asked = run.asked.get(row["slug"], "") if found["status"] == "pr" else ""
    if row.get("held") and failed_twice(run, row["slug"]) and not asked:
        return TWICE
    if found["status"] == "pr":
        said = waits.said.get(found["pr"].removeprefix("#"))
        if said is None and waits.failed and row.get("status") == "pr":
            return row.get("why", "")
        return "; ".join(one for one in (asked, said) if one)
    if found["status"] not in ("queued", "gate"):
        return ""
    match run.reasons.get(row["slug"]):
        case Changed(sha):
            return f"brief changed after approval, now {sha}"
        case Depends(slugs):
            return f"depends on {', '.join(slugs)}"
        case Slot(why=said):
            return said or "no slot"
        case Rerun(sha):
            return f"main is green again at {sha}, its own commit, so it has no red to fix"
        case Red():
            return "main is red: waits for green"
    if found["status"] == "gate":
        return GATED
    if not row.get("approved"):
        return "not approved"
    if unread != UNREAD:
        return unread
    kept = row.get("why", "") if row.get("status") in ("queued", "gate") else ""
    return "" if kept == "not approved" or budgethold.held_why(kept) else kept


def watch(run: Pass, world: World, rows: list[dict[str, Any]]) -> None:
    """Send a line for each thing a home would have seen, and a gate for what no rule covers.

    The thread of a queue row that completed with a Result is no gate: its row says how it
    ended (`ended`).
    """
    queued = {row["slug"] for row in rows}
    for slug, live in world.threads.items():
        if len(live) > 1:
            run.gate(
                slug, f"{len(live)} threads for one slug", "\n".join(t["threadId"] for t in live)
            )
        elif live[0]["status"] not in KNOWN:
            run.gate(slug, f"thread state {live[0]['status']} jbus does not know")
    for branch, pull in world.open.items():
        if not brief_of(run, branch):
            run.gate(branch, f"pull request #{pull['number']} has no brief", pull.get("url", ""))
    for slug, live in world.threads.items():
        if slug in run.gated:
            continue
        thread, line = live[0], _stale(run, world, slug, live[0])
        if line:
            fact = thread["updatedAt"] if thread["status"] == "waiting" else thread["status"]
            run.find(slug, "stale", line, key=f"{thread['threadId']} {fact}")
        elif thread["status"] == "completed" and slug not in {*world.open, *world.merged, *queued}:
            run.gate(slug, "thread completed with a Result and no pull request")
    for slug, thread in world.archived.items():
        taken = slug in world.open or slug in world.merged
        if slug not in queued or slug in run.gated or taken:
            continue
        if not last_result(brief_of(run, slug)):
            line = f"stale {slug}: thread {thread['threadId']} is archived with no Result"
            run.find(slug, "stale", line, key=f"{thread['threadId']} archived")
    for slug, pull in world.merged.items():
        if slug in run.gated or not (brief := brief_of(run, slug)):
            continue
        commit = (pull.get("mergeCommit") or {}).get("oid", "")
        line = f"merged {slug} #{pull['number']} {commit[:12]}"
        result = last_result(brief)
        run.find(slug, "merged", line, result, key=f"#{pull['number']}", past=True)
    nightlies = watched(run)
    read = side_by_side(lambda nightly: _nightly_runs(run, nightly), nightlies)
    for nightly, runs in zip(nightlies, read, strict=True):
        _nightly_red(run, nightly, runs)


BRIEFS_SEEN = "briefs-seen.json"
"""What `rewritten` saw last of each launched row's brief, from its first `## ` heading on."""
REWRITTEN = (
    "jbus: tasks/{slug}.md lost lines since the last pass. A later round never rewrites a Result "
    "or any section under it: it appends. These lines went, word for word:\n\n```\n{lines}\n```"
    "\n\nPut them back as they were. A correction is a new `## Result, follow-up (<date>, <why>)` "
    "section at the end of the brief."
)


IN_PLACE = (stacks.LINE, "Fixed:", "Scoped reviewer:")
"""The lines of a Result that are rewritten in place by rule: jbus moves a `Stacked on:` line
(`jbus.stack`), and the crew skill sets its `Fixed:` line to the head it pushed again and puts a
new `Scoped reviewer:` line in place of one that stopped."""


def sections_of(brief: str) -> str:
    """The part of a brief that its crew and reviewers append to: from its first `## ` heading on,
    with no line of `IN_PLACE`. The head above it is the home's and jbus's."""
    _, mark, rest = brief.partition("\n## ")
    if not mark:
        return ""
    lines = ("## " + rest).splitlines(keepends=True)
    return "".join(line for line in lines if not line.startswith(IN_PLACE))


def dropped(old: str, new: str) -> list[str]:
    """The lines of `old` that `new` no longer has, blank ones aside, or none where `new` only
    grew `old`."""
    if new.startswith(old):
        return []
    was, now = old.splitlines(), new.splitlines()
    return [
        line
        for tag, i1, i2, _, _ in SequenceMatcher(None, was, now, autojunk=False).get_opcodes()
        if tag in ("delete", "replace")
        for line in was[i1:i2]
        if line.strip()
    ]


def rewritten(run: Pass, client: Client, rows: list[dict[str, Any]] | None) -> None:
    """Tell a launched row's thread once when its brief lost lines it had on the pass before: a
    later round appends a `## Result, follow-up` and never rewrites a section (the crew skill's
    "End"). A message the outbox holds keeps the old text, so a later pass sends it. A queue
    that does not parse (`rows` None) leaves what was seen as it was. `jbus.outbox` reads this
    module, so this one reads `outbox` at the call."""
    from jbus import outbox

    if rows is None:
        return
    kept: dict[str, str] = read_json(run.state / BRIEFS_SEEN, {})
    seen: dict[str, str] = {}
    for row in rows:
        slug = row["slug"]
        thread = (
            thread_of(run.home, slug)
            if queue.role(row) == queue.CREW and not queue.over(row)
            else ""
        )
        if not thread:
            continue
        new = sections_of(task_brief(run, slug))
        old = kept.get(slug)
        seen[slug] = new
        lines = dropped(old, new) if old is not None else []
        if old is None or not lines:
            continue
        key = f"rewritten|{slug}|{hashlib.sha256((old + new).encode()).hexdigest()[:16]}"
        text = REWRITTEN.format(slug=slug, lines="\n".join(lines))
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=slug,
                key=key,
                text=text,
                template="rewritten",
                needs="act",
            )
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told its brief lost lines ({error})")
            went = False
        if went:
            many = "" if len(lines) == 1 else "s"
            run.say(f"rewritten {slug}: told its crew the brief lost {len(lines)} line{many}")
        else:
            seen[slug] = old
    if seen != kept:
        write_json(run.state / BRIEFS_SEEN, seen)


def _api(run: Pass, path: str) -> Any:
    """Return what GitHub answers a GET of `path`, or None where it gives no answer. A path the
    pass already read is answered from `Pass.answers`, without a call."""
    if path in run.answers:
        return run.answers[path]
    asked = run.run("gh", "api", path)
    try:
        said = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        said = None
    if said is not None:
        run.answers[path] = said
    return said


MAIN_COMMITS = "main-commits.json"
"""Main's newest `MAIN_LISTED` commits, as GitHub lists them, with the tip they were read at:
`{tip, commits}`."""
MAIN_LISTED = 50
WORKFLOW_FILES = "workflow-files.json"
"""The `.github/workflows/` tree GitHub gave `watched`, with the tip it was read at:
`{tip, tree}`."""


def _at_tip(
    run: Pass, name: str, key: str, ask: Callable[[str], Any], keeps: Callable[[Any, str], bool]
) -> Any:
    """Return what `ask` answers for main's tip, kept in the file `name` of the project's state
    under `key` with that tip, where `keeps` finds the answer is the tip's. A commit's history
    and its files never change, so it is asked again only once the tip is another (`Pass.tip`).
    Where git gives no tip, `ask` is given the default branch's name, and nothing is kept."""
    tip = run.tip()
    if not tip:
        return ask(_default_branch(run))
    path = run.state / name
    kept = read_json(path, {})
    if isinstance(kept, dict) and kept.get("tip") == tip and key in kept:
        return kept[key]
    said = ask(tip)
    if keeps(said, tip):
        write_json(path, {"tip": tip, key: said})
    return said


def main_commits(run: Pass) -> Any:
    """Main's newest `MAIN_LISTED` commits, newest first, as GitHub's list of commits gives
    them, or None where it gives no answer. One read for each tip of main (`_at_tip`): a list
    is kept only where it starts at that tip."""
    return _at_tip(
        run,
        MAIN_COMMITS,
        "commits",
        lambda at: _api(run, f"repos/{{owner}}/{{repo}}/commits?sha={at}&per_page={MAIN_LISTED}"),
        lambda said, tip: isinstance(said, list) and bool(said) and said[0].get("sha") == tip,
    )


def _check(
    run: Pass, known: dict[str, str], sha: str, again: bool = False, rerun: bool = False
) -> str:
    """Return whether the check runs of a commit on main passed. `_check` asks GitHub once
    for a final answer, and keeps it in `known`.

    Main's check is its push run's: only the check runs `_judged` gives count. A run of
    browser.yml or any other workflow dispatched by hand, on a schedule or for a tag at the same
    commit says nothing of main's check, and its red has its own path (`BROWSER`, `NIGHTLIES`).

    A cancelled run is no failed check. A push run cancelled before it had a job leaves the commit
    with no check run at all: pushes to main share one concurrency group, where a newer push, or the
    rerun of an older push's failed run, displaces the run that waits. Under main's tip, the next
    run that runs selects over every merge since the last checked commit, so the commit is
    `BATCHED`, final, and never rerun: a rerun would join the group and displace the newest push's
    run in turn. A red over a batch is judged as a red with several commits since the last green
    (`jbus.reverts.culprit`). At main's tip, which `again` asks of, a kept `BATCHED` is asked again,
    since no later push covers it, as where jbus's own rerun of a failed run displaced it: there, as
    for a run someone stopped once it had jobs, a cancelled run at its first attempt is rerun, the
    rerun selects over every merge since the last checked commit, and the commit is `pending` until
    the rerun ends. GitHub's `run_attempt` says whether the run ran again: `cancelled` is a later
    attempt that was cancelled too, and `refused` a run that GitHub did not start again.

    A failed push run is rerun once before the commit is `failed`, since most of main's reds
    were flakes that passed on a second attempt. With `rerun`, `_check` reruns the failed jobs
    of each failed push run at its first attempt (`gh run rerun --failed`), and the commit is
    `pending` while any push run has not ended. A run at a later attempt, rerun by jbus or by
    hand, is never rerun again: its failure is the commit's. jbus asks for each run's rerun
    once (`_rerun_failed`): where GitHub refuses it, or still shows the first attempt
    `RERUN_WAIT` after, the commit is `failed`. An ask is kept for a day (`RETRO`).

    A commit whose every failed check run has a job that ran no step, and no check run of which
    passed, is `NO_JOB`, not `failed`: GitHub started no job, as on a spent Actions limit or a
    failed payment, so no code was judged. A run that passed shows that GitHub starts jobs, so a
    run beside it that started none is a failed check. A check run whose job GitHub does not give
    counts as one that ran, as in `never_started`.
    """
    if sha in known and not (again and known[sha] == BATCHED):
        return known[sha]
    known.pop(sha, None)
    runs, pushed = _judged(run, sha)
    if (
        not again
        and not runs
        and pushed
        and all(r.get("conclusion") == "cancelled" for r in pushed)
    ):
        known[sha] = BATCHED
        return BATCHED
    ended = [r.get("conclusion") for r in runs if r.get("status") == "completed"]
    if len(ended) < len(runs):
        return "pending"
    failed = [r for r in runs if r.get("conclusion") not in NOT_RED]
    unrun = (job(run, "{owner}/{repo}", str(r.get("id"))).get("steps") == [] for r in failed)
    if failed and "success" not in ended and all(unrun):
        known[sha] = NO_JOB
        return NO_JOB
    bad = bool(failed)
    if bad and any(r.get("status") != "completed" for r in pushed):
        return "pending"
    first = [
        r for r in pushed if r.get("conclusion") not in NOT_RED and (r.get("run_attempt") or 1) == 1
    ]
    if bad and first and _rerun_failed(run, first, ask=rerun):
        return "pending"
    if bad or (runs and "cancelled" not in ended):
        known[sha] = "failed" if bad else "green"
        return known[sha]
    stopped = [r for r in pushed if r.get("conclusion") == "cancelled"]
    if not stopped or any(r.get("status") != "completed" for r in pushed):
        return "pending"
    if any((r.get("run_attempt") or 1) > 1 for r in stopped):
        known[sha] = "cancelled"
    elif again and any(
        run.run("gh", "run", "rerun", str(r["id"])).returncode != 0 for r in stopped
    ):
        known[sha] = "refused"
    return known.get(sha, "pending")


def _rerun_failed(run: Pass, first: list[dict], ask: bool) -> bool:
    """Rerun the failed jobs of each push run at its first attempt, once, and return whether
    each rerun is still to be waited on. Only with `ask` does it ask GitHub for a rerun not
    asked for yet; without it, such a run is failed.

    `RERUNS` keeps when jbus asked for each and whether GitHub took it, so a run GitHub still
    shows at its first attempt is not asked again: it is waited on for `RERUN_WAIT`, and is
    then failed, as is a run whose rerun GitHub refused. An ask is kept for a day (`RETRO`)."""
    path = run.state / RERUNS
    asked: dict[str, dict] = read_json(path, {})
    waiting = True
    for one in first:
        key = str(one.get("id"))
        if key not in asked and not ask:
            return False
        if key not in asked:
            took = run.run("gh", "run", "rerun", "--failed", key).returncode == 0
            asked[key] = {"at": run.now.isoformat(), "took": took}
        since = run.now - when(asked[key]["at"])
        waiting = waiting and asked[key]["took"] and since < RERUN_WAIT
    write_json(path, {key: one for key, one in asked.items() if run.now - when(one["at"]) < RETRO})
    return waiting


def _judged(run: Pass, sha: str) -> tuple[list[dict], list[dict]]:
    """Return the check runs that judge a commit on main, and its push runs on the default
    branch. A check run counts unless it belongs to another workflow run at the commit: one not
    run by a push to the default branch. Where GitHub does not list the commit's workflow runs,
    every check run counts. macos.yml's push run is never main's check, nor are its jobs by
    their names where GitHub lists no run: a Mac red has its own path (`mac_check`,
    `jbus.reverts.macos`), and never makes main red."""
    said = _api(run, _runs_of(sha))
    listed = (said if isinstance(said, dict) else {}).get("workflow_runs") or []
    branch = _default_branch(run)
    pushed = [
        r
        for r in listed
        if r.get("event") == "push" and r.get("head_branch") == branch and not _of_mac(r)
    ]
    other = {r.get("check_suite_id") for r in listed if r not in pushed} - {None}
    said = _api(run, _check_runs_of(sha))
    runs = (said if isinstance(said, dict) else {}).get("check_runs") or []
    return [
        r
        for r in runs
        if (r.get("check_suite") or {}).get("id") not in other and not mac_job(r.get("name"))
    ], pushed


def unjudged(run: Pass, sha: str) -> bool:
    """Return whether GitHub answered both of `_judged`'s reads of a commit in this pass, and
    they give it no check run that judges it and no push run, as for a commit pushed while
    check.yml is disabled, a commit that rode in on a later push, or a pull request's head.
    `_check` answers such a commit `pending`. It asks GitHub nothing: only the pass's own answers
    count (`Pass.answers`)."""
    answered = all(isinstance(run.answers.get(at(sha)), dict) for at in (_runs_of, _check_runs_of))
    return answered and _judged(run, sha) == ([], [])


def _runs_of(sha: str) -> str:
    return f"repos/{{owner}}/{{repo}}/actions/runs?head_sha={sha}&per_page=100"


def _check_runs_of(sha: str) -> str:
    return f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs"


MAC_FLOW = ".github/workflows/macos.yml"
MAC_JOBS = ("macos-select", "macos")
"""macos.yml, and its jobs' names: its run on each push to main judges that merge commit on a
Mac, apart from main's check. `macos-select` and the gate `macos` run on Linux; the Mac runs
are the parts (`MAC_PART`), and `macos` passes only when every part did."""
MAC_PART = re.compile(r"macos \d+ of \d+")
"""The name of each part of macos.yml's Mac tests, `macos K of N`, each on its own Mac."""


def mac_job(name: object) -> bool:
    """Return whether a job's name is one of macos.yml's: `macos-select`, `macos`, or a part
    `macos K of N`."""
    return isinstance(name, str) and (name in MAC_JOBS or bool(MAC_PART.fullmatch(name)))


def _of_mac(one: dict) -> bool:
    return str(one.get("path") or "").partition("@")[0] == MAC_FLOW


def mac_runs(run: Pass, sha: str) -> list[dict] | None:
    """The runs of macos.yml for the push of a commit to the default branch, or None where GitHub
    does not list the commit's runs."""
    said = _api(run, _runs_of(sha))
    if not isinstance(said, dict):
        return None
    branch = _default_branch(run)
    return [
        r
        for r in said.get("workflow_runs") or []
        if _of_mac(r) and r.get("event") == "push" and r.get("head_branch") == branch
    ]


def mac_check(run: Pass, known: dict[str, str], sha: str) -> str:
    """Return what macos.yml's push run says of a commit on main, and keep a final answer in
    `known`: `green` where its job `macos` ran and passed, `skipped` where the run passed with
    that job skipped, as for a change that reaches no Mac test, so nothing was judged on a Mac,
    `failed` where it failed after its one rerun, `cancelled` where it was stopped, `pending`
    while it runs or its rerun does, or GitHub gives no answer, and an empty string where the
    commit has no such run. A failed run at its first attempt is rerun once (`_rerun_failed`), as
    main's check is."""
    if sha in known:
        return known[sha]
    runs = mac_runs(run, sha)
    if runs is None or any(r.get("status") != "completed" for r in runs):
        return "pending"
    if not runs:
        return ""
    failed = [r for r in runs if r.get("conclusion") not in NOT_RED]
    first = [r for r in failed if (r.get("run_attempt") or 1) == 1]
    if first and _rerun_failed(run, first, ask=True):
        return "pending"
    stopped = any(r.get("conclusion") == "cancelled" for r in runs)
    if failed or stopped:
        known[sha] = "failed" if failed else "cancelled"
        return known[sha]
    said = _api(run, _check_runs_of(sha))
    if not isinstance(said, dict):
        return "pending"
    suites = {r.get("check_suite_id") for r in runs} - {None}
    ran = [
        one
        for one in said.get("check_runs") or []
        if (one.get("check_suite") or {}).get("id") in suites
        and one.get("name") == MAC_JOBS[-1]
        and one.get("conclusion") == "success"
    ]
    known[sha] = "green" if ran else "skipped"
    return known[sha]


def mac_jobs(run: Pass, sha: str) -> list[tuple[str, str, Failed]] | None:
    """Each failed job of macos.yml's push run at a commit, with its URL and the tests its log
    names, or None where GitHub gives no answer or a log could not be read. The gate `macos`
    fails whenever a part did and names no test, so it is left out where a part failed."""
    runs = mac_runs(run, sha)
    said = _api(run, _check_runs_of(sha))
    if runs is None or not isinstance(said, dict):
        return None
    suites = {r.get("check_suite_id") for r in runs} - {None}
    failed = [
        one
        for one in said.get("check_runs") or []
        if (one.get("check_suite") or {}).get("id") in suites
        and one.get("status") == "completed"
        and one.get("conclusion") not in NOT_RED
    ]
    if any(MAC_PART.fullmatch(str(one.get("name") or "")) for one in failed):
        failed = [one for one in failed if one.get("name") != MAC_JOBS[-1]]
    jobs = []
    for one in failed:
        found = _log_failed(run, one.get("id"))
        if found is None:
            return None
        jobs.append((str(one.get("name") or "?"), str(one.get("html_url") or ""), found))
    return jobs


def job_log(run: Pass, repo: str, job: object) -> str | None:
    """Return a job's log, or None where GitHub did not give it. GitHub's log has escape
    sequences in it, which gh 2.102 gives only when asked to. A job's id is GitHub's own, so once
    the pass has its world, the first read of a job's log is the pass's answer (`World.logs`)."""
    kept = run.world.logs if run.world is not None else {}
    if str(job) not in kept:
        path = f"repos/{repo}/actions/jobs/{job}/logs"
        log = run.run("gh", "api", path, "--allow-escape-sequences")
        kept[str(job)] = log.stdout if log.returncode == 0 else None
    return kept[str(job)]


def _log_failed(run: Pass, job: object) -> Failed | None:
    """Return the tests that a job's log reports as failed, or None where jbus could not read
    the log."""
    log = job_log(run, "{owner}/{repo}", job)
    return None if log is None else failed_in(log)


def tests_said(jobs: list[tuple[str, str, Failed]]) -> str:
    """Return how many tests the failed jobs report, and how many of them they name."""
    count = sum(failed.count for _, _, failed in jobs)
    named = sum(len(failed.tests) for _, _, failed in jobs)
    tests = f"{count} test{'' if count == 1 else 's'}"
    if count == named:
        return f"{tests} named"
    return f"{tests} failed, {named or 'none'} named"


def fix_brief(
    heading: str,
    task: str,
    done: Sequence[str],
    proves: str,
    filed: str,
    jobs: Sequence[tuple[str, str, Sequence[str]]],
    read: Sequence[str] = (),
    *,
    files: Sequence[str] = (),
    nowhere: str = "",
    pull: str = "open one when done",
    home: str = "",
    follows: str = "",
) -> str:
    """Return the brief for the fix of a red check that jbus files, in the shape of
    `features/jbriefs/templates/brief.md`: of a red main (`_file`) or a red nightly run
    (`_nightly_red`). `jobs` is each failed job's name, URL and failed tests, which `Read` names
    before the lines of `read`. `Where` names `files`, then the file of each failed test, less any
    shared doc a fix brief may not claim (`queue.shared_doc`), or says
    `nowhere` where there are none. `filed` is what jbus filed it from, and
    `follows` the row whose work the fix is a follow-up of: a pass approves it on that row's go
    (`queue.follow_ups`). Its `Home:` line is `home`, a scope's name, or `uncategorized`, so that
    a home can queue it again as `jbus queue add` asks."""
    tests = [test for _, _, failed in jobs for test in failed]
    where = [
        file
        for file in dict.fromkeys([*files, *(test.split("::")[0] for test in tests)])
        if not queue.shared_doc(f"`{file}`")
    ]
    return "\n".join(
        [
            f"# {heading}",
            f"Task: {task}",
            "Done when:",
            *done,
            f"Proves it: {proves}",
            "Size: S",
            f"Where: {', '.join(f'`{file}`' for file in where) or nowhere}",
            "Do not touch: .github/workflows/, the ruleset",
            f"Decisions: {queue.RED_DECIDED}{filed} and the user has not seen it",
            "Design: none, a fix to what the failed run names",
            f"Pull request: {pull}",
            "Review: review",
            "Playbook: bug-fix",
            "Skills: tdd",
            f"Home: {home or homes.UNCATEGORIZED}",
            *([f"Follows: {follows}"] if follows else []),
            "Read:",
            *(
                f"- the job `{name}`, {url or 'with no URL'}: "
                + (
                    ", ".join(f"`{test}`" for test in failed)
                    or "its log names no failed test, read it"
                )
                for name, url, failed in jobs
            ),
            *read,
            "",
        ]
    )


_JOB = re.compile(r"- the job `([^`]*)`, (?:with no URL|\S+): (.*)")

Failure = frozenset[tuple[str, frozenset[str]]]


def failure_of(jobs: Iterable[tuple[str, str, Sequence[str]]]) -> Failure:
    """Return what a red run failed, by each failed job's name and its failed tests, with no URL,
    since each run's jobs have URLs of their own."""
    return frozenset((name, frozenset(tests)) for name, _, tests in jobs)


def named_failure(brief: str) -> Failure:
    """Return the failure a fix brief names on its `Read:` lines of each failed job, as
    `fix_brief` writes them."""
    jobs = []
    for line in brief.splitlines():
        if found := _JOB.fullmatch(line):
            tests = re.findall(r"`([^`]*)`", found[2])
            jobs.append((found[1], "", tests))
    return failure_of(jobs)


def _open_reds(run: Pass) -> list[tuple[dict[str, Any], str]]:
    """Return each open fix row of a red main with its brief, as its crew reads it in `tasks/`,
    or as the queue keeps it where `tasks/` has none."""
    try:
        rows = queue.load(run.state)
    except queue.Unparsable:
        return []
    found = []
    for row in rows:
        if not mainjson.fix_of(row["slug"]) or row.get("status") in queue.FINAL:
            continue
        path = run.home / "tasks" / f"{row['slug']}.md"
        brief = path.read_text() if path.exists() else queue.brief(run.state, row["slug"]) or ""
        found.append((row, brief))
    return found


def _same_red(run: Pass, failure: Failure) -> tuple[dict[str, Any], str] | None:
    """Return the open fix row of a red main, and its brief, whose failed jobs and tests are
    `failure`, or None where no open row fails as it does."""
    if not failure:
        return None
    return next(((r, b) for r, b in _open_reds(run) if named_failure(b) == failure), None)


def _add_tip(run: Pass, row: dict[str, Any], brief: str, sha: str, red: list[dict]) -> None:
    """Add the red tip `sha` to the brief of `row`, the open fix row of the red it fails as, and
    file no row of its own: one break gets one fix row, however many merges land on top of it.
    The line goes under `Read:`, which the row's go does not cover (`jbriefs.meaning`), so the go
    holds. A row that never launched is queued again with the brief, as its launch reads it beside
    `tasks/`; a launched row's crew reads it in `tasks/`."""
    name = row["slug"]
    merge = red[0]["commit"]["message"].splitlines()[0] if red else "no merge"
    line = f"- main is red again at {sha[:12]} with the same failed jobs and tests, after {merge}"
    lines = brief.splitlines()
    at = next((n for n, one in enumerate(lines) if one.startswith("## ")), len(lines))
    while at and not lines[at - 1].strip():
        at -= 1
    text = "\n".join([*lines[:at], line, *lines[at:]]) + "\n"
    (run.home / "tasks").mkdir(parents=True, exist_ok=True)
    (run.home / "tasks" / f"{name}.md").write_text(text)
    if not row.get("thread") and row.get("status") in queue.UNLAUNCHED:
        priority, depends = row.get("priority", 0), row.get("depends", [])
        try:
            queue.add(run.state, name, priority, depends, text, user=run.user, ran_by=queue.PASS)
        except (Refused, queue.Unparsable) as refused:
            run.condition(name, f"its brief did not take main's red tip {sha[:12]}: {refused}")
    said = f"retro {name}: main is red again at {sha[:12]} as it is, and its row names the tip"
    run.find(name, "retro", said, key=f"same red {sha}", past=True)


def _changed(run: Pass, red: list[dict]) -> list[str]:
    """Return the files the commits changed, as GitHub lists them for each."""
    files = []
    for commit in red:
        said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{commit['sha']}")
        listed = said.get("files") if isinstance(said, dict) else None
        files += [one.get("filename", "") for one in listed or []]
    return [file for file in dict.fromkeys(files) if file]


FIX_GOES = (
    "- the fix is in a pull request of its own, or in another open pull request only where that "
    "one waits on no other open pull request: no `merge_after` row still open (jmerge's "
    "`merges after` or `carries ... which merges after`) and not stacked on an open base "
    "(`it is stacked on`); otherwise the crew opens its own pull request with the fix, and "
    "whichever of the two merges second rebases"
)
"""The line of main's fix brief that says where its fix may go. jmerge judges a pull request
whose check failed over a red main again only once main is green, so a fix left in a pull
request that merges after that one, or is stacked on it, would wait on the green it makes
(features/jmerge/spec/FlowToday.tla `Unordered(q)`)."""


def _file(run: Pass, slug: str, sha: str, red: list[dict], kept: str = "") -> None:
    """Write the brief for the fix of a red main to the home's `tasks/`, and queue it with no
    approval. Where a briefed merge turned main red, the brief follows that row and a pass
    approves it on the row's go; otherwise a pass approves it by the follow-up rule with no
    parent, since jbus filed it (`queue.follow_up`). Its `Done when:` ends `FIX_GOES`. Its priority
    is one above the first row of the queue, so once approved it is the next launch there.
    A red tip whose failed jobs and tests are the ones an open fix row names is the same break,
    with more merges on top of it: `_file` files no row for it and adds the tip to that row's
    brief (`_add_tip`). Only a run known by its tests (`mainjson.failures`) is the same break:
    a job that names none, a lint or a timeout, may fail for another reason at each tip.
    `_file` writes the brief whenever the queue has no row for it. So if a pass stopped before
    it added the row, the next pass files the brief again. If the queue
    refuses the brief, that is a condition. `kept` says why jbus reverted nothing (`_revert`),
    which its task names."""
    name = f"{mainjson.FIX}{sha[:12]}"
    if name in run.removed or queue.fresh(run.state, name) is not None:
        return
    if any(sha[:12] in brief for _, brief in _open_reds(run)):
        return
    runs, pushed = _judged(run, sha)
    logs = [
        (r.get("name") or "?", r.get("html_url") or "", _log_failed(run, r.get("id")) or Failed())
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") not in NOT_RED
    ]
    jobs = [(name, url, list(failed.tests)) for name, url, failed in logs]
    known = mainjson.failures([(name, failed.tests, failed.count) for name, _, failed in logs])
    if known and (same := _same_red(run, failure_of(jobs))):
        _add_tip(run, *same, sha, red)
        return
    reran = [
        (r.get("name") or "?", r.get("html_url") or "", r["run_attempt"])
        for r in pushed
        if r.get("conclusion") not in NOT_RED and (r.get("run_attempt") or 1) > 1
    ]
    after = f"after {slug} merged" if slug else "with no briefed merge in the day before it"
    text = fix_brief(
        f"{name}: main's check failed at {sha[:12]}, {after}",
        f'"main check failed at {sha[:12]}, {len(red)} merges since the last green" '
        + (f"(jbus, the retro of {slug})" if slug else "(jbus, the retro of main's tip)")
        + (f". jbus reverts nothing: {kept}" if kept else ""),
        [
            "- each failed test named under Read passes on main, and the failed job passes at "
            "the commit that merges the fix",
            "- the Result names the cause: the merge that broke main, or a flake with its evidence",
            FIX_GOES,
        ],
        "CI's check on main passes at the commit that merges the fix",
        "main",
        jobs,
        [
            *(
                f"- the push run `{job}` failed at its first attempt, {url}/attempts/1, "
                f"and again when it ran again, {url}/attempts/{attempt}"
                for job, url, attempt in reran
            ),
            *(
                f"- the merge {commit['sha'][:12]} {commit['commit']['message'].splitlines()[0]}"
                for commit in red
            ),
        ],
        files=_changed(run, red),
        nowhere="`.` (the whole repo: the merges since the last green changed files nobody listed)",
        follows=slug,
    )
    (run.home / "tasks").mkdir(parents=True, exist_ok=True)
    (run.home / "tasks" / f"{name}.md").write_text(text)
    try:
        top = min((row.get("priority", 0) for row in queue.load(run.state)), default=1) - 1
        queue.add(run.state, name, top, [], text, user=run.user, ran_by=queue.PASS)
    except (Refused, queue.Unparsable) as refused:
        run.condition(name, f"its brief was not queued: {refused}")


def _default_branch(run: Pass) -> str:
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    return default.stdout.strip().removeprefix("origin/") or "main"


@dataclass(frozen=True)
class Nightly:
    """A workflow that no required check runs, whose red run on the default branch, or of a
    release, jbus files a fix brief for. Its run for a pull request, or by hand on another branch,
    files nothing (`_nightly_red`).

    `file` is the workflow's file, `prefix` the slug's start before the day, `seen` the file in
    the project's state that keeps the runs jbus has seen, and `run` how the run is named. The
    rest are the brief's own lines: `failed` what failed, `where` its `Where:` when the log
    names no test, `done` and `proves` how the fix is shown, `pull` its `Pull request:`, and
    `home` the scoped home it is filed under, or an empty string for the root home, and `filed`
    the red the brief's `Decisions:` line says it was filed from. `events`, where it is set, are
    the only events whose runs are filed: a workflow that also runs on a push to the default
    branch has that run judged as main's check (`_judged`), so its red is main's red. `title`,
    where it is set, is the title of the runs jbus files for: a run of the workflow with any
    other title checked out another ref, and is that ref's concern. `branch`, where it is set, is
    the branch those runs check out: until one run of it there has passed, its red runs are that
    branch's known work, which its home's plan holds, and file no row.
    """

    file: str
    prefix: str
    seen: str
    run: str
    failed: str
    where: str
    done: str
    proves: str
    pull: str = "open one when done"
    home: str = ""
    title: str = ""
    branch: str = ""
    filed: str = "nightly run"
    events: tuple[str, ...] = ()


BROWSER = Nightly(
    file="browser.yml",
    prefix="browser-red-",
    seen="browser-runs.json",
    run="the browser run",
    failed="the browser tests failed",
    where="the tests marked `browser`",
    done="each failed test named under Read passes under `make check-browser`",
    proves="`make check-browser` passes, and so does a manual run of browser.yml "
    "(workflow_dispatch) on the fix's branch",
)
MACOS = Nightly(
    file="macos-nightly.yml",
    prefix="macos-red-",
    seen="macos-nightly-runs.json",
    run="the macOS nightly run",
    failed="the macOS suite failed",
    where="the tests the macOS nightly runs on main, under `features/` and `testing/`",
    done="each failed test named under Read passes on macOS, in a manual run of "
    "macos-nightly.yml with `ref` set to the fix's branch",
    proves="the touched check, `make check-fast BASE=origin/main PART=touched`, passes, and so "
    "does a manual run of macos-nightly.yml (`gh workflow run macos-nightly.yml -f ref=<the "
    "fix's branch>`)",
    pull="open one when done",
    home="macos",
    title="macos-nightly on main",
    branch="main",
)
NIGHTLIES = (BROWSER, MACOS)
"""The nightly workflows with their own brief for a red run (`_nightly_red`). Every other
scheduled workflow gets the brief `scheduled` gives it (`watched`)."""
WORKFLOWS = (
    "query($owner: String!, $repo: String!, $at: String!) { repository(owner: $owner, name: $repo)"
    " { object(expression: $at) { ... on Tree { entries { name object { ... on Blob { text } } } }"
    " } } }"
)
"""The GraphQL query for the text of each file of a tree, `$at` as `<commit>:.github/workflows`,
in one call."""
SCHEDULED_EVENTS = ("schedule", "workflow_dispatch")
"""The events of a scheduled workflow's runs that `scheduled` files: its push runs on the default
branch are main's check (`_judged`), and its release runs are no concern of the schedule's."""
SCHEDULE = re.compile(r"^\s+schedule:\s*(#.*)?$", re.MULTILINE)
"""A workflow's `schedule:` trigger, a key under `on:` with its crons under it."""
NIGHTLY_RELEASE = ("push", "release")
"""The events of a nightly's run off the default branch that are still filed: a release's tag,
since no nightly runs on a push to a branch (`_nightly_red`)."""


def scheduled(file: str) -> Nightly:
    """The rule for a red run of the scheduled workflow `file` that is none of `NIGHTLIES`: its
    row is `red-<stem>-<day>`, a slug no other filer's prefix starts, filed for the root home."""
    stem = file.rsplit(".", 1)[0]
    return Nightly(
        file=file,
        prefix=f"red-{stem}-",
        seen=f"scheduled-{stem}-runs.json",
        run=f"the {stem} run",
        failed=f"{file} failed",
        where=f"what the failed jobs of `.github/workflows/{file}` run",
        done=f"the failure named under Read is fixed, and a run of {file} on the fix's branch "
        "passes where the workflow can be run by hand",
        proves=f"the commands the failed jobs of {file} run pass on the fix's branch, and so does "
        f"a manual run of {file} (`gh workflow run {file} --ref <the fix's branch>`) where it "
        "has a `workflow_dispatch:` trigger",
        filed="scheduled run",
        events=SCHEDULED_EVENTS,
    )


def watched(run: Pass) -> list[Nightly]:
    """The workflows whose red run on the default branch jbus files a fix row for: each of
    `NIGHTLIES` the repo holds, with its own rule, and each other file of `.github/workflows/`
    with a `schedule:` trigger at the default branch (`scheduled`). jbus asks GitHub for the files
    at main's tip, since no step of a pass is sure to fetch, once for each tip (`_at_tip`), so a
    repo that adds a nightly is watched from the pass that sees its merge, and one that lacks it
    costs no call for its runs, a 404. Where GitHub gives no list of the files, it watches
    `NIGHTLIES` alone."""
    tree = _at_tip(
        run,
        WORKFLOW_FILES,
        "tree",
        lambda at: _workflows(run, at),
        lambda said, _: said is not None,
    )
    entries = tree.get("entries") if isinstance(tree, dict) else None
    if not isinstance(entries, list):
        return list(NIGHTLIES)
    names = {entry.get("name") for entry in entries if isinstance(entry, dict)}
    own = {nightly.file for nightly in NIGHTLIES}
    found = sorted(
        entry["name"]
        for entry in entries
        if isinstance(entry, dict)
        and str(entry.get("name", "")).endswith((".yml", ".yaml"))
        and entry["name"] not in own
        and SCHEDULE.search((entry.get("object") or {}).get("text") or "")
    )
    held = [nightly for nightly in NIGHTLIES if nightly.file in names]
    return [*held, *map(scheduled, found)]


def _workflows(run: Pass, at: str) -> dict[str, Any] | None:
    """The tree of `.github/workflows/` at the commit or branch `at`, as `WORKFLOWS` asks
    GitHub for it: empty where there is no such tree, and None where GitHub gives no answer."""
    asked = run.run(
        "gh",
        "api",
        "graphql",
        "-F",
        "owner={owner}",
        "-F",
        "repo={repo}",
        "-f",
        f"query={WORKFLOWS}",
        "-f",
        f"at={at}:.github/workflows",
    )
    if asked.returncode != 0:
        return None
    try:
        tree = json.loads(asked.stdout)["data"]["repository"]["object"]
    except (ValueError, KeyError, TypeError):
        return None
    return tree if isinstance(tree, dict) else {}


def ran_at(one: dict[str, Any]) -> str:
    """The line of a brief's `Read:` that names a nightly's run, the event it ran on and its
    commit."""
    number, event = one.get("id"), one.get("event") or "an event"
    return f"- the run {one.get('html_url') or number}, from {event}, at {one.get('head_sha')}"


def drawn_apart(
    jobs: list[tuple[str, str, Failed]], logs: list[str]
) -> tuple[list[tuple[str, str, list[str]]], list[tuple[str, str, Failed]]]:
    """Split the failed jobs of a nightly's run, with each job's log, into its shot tests, the
    shots row's (`shots.drawn`), and the rest, each job with the tests of its part: a job whose
    failures are all named shot tests that said a shot moved is in the rest no longer, and a job
    that names none is. Where fewer of a job's tests said a shot moved (`shots.moved_in`) than
    shot tests failed, one failed some other way, and its job's shot tests are in the rest too."""
    drawn, rest = [], []
    for (job, url, failed), log in zip(jobs, logs, strict=True):
        moved = [test for test in failed.tests if shots.drawn(test)]
        crashed = len(moved) > shots.moved_in(log)
        if moved:
            drawn.append((job, url, moved))
        if not moved or crashed or failed.count > len(moved):
            others = tuple(test for test in failed.tests if crashed or not shots.drawn(test))
            rest.append((job, url, Failed(others, failed.count - (0 if crashed else len(moved)))))
    return drawn, rest


def _filed(run: Pass, nightly: Nightly, name: str, text: str, number: str, said: str) -> bool:
    """Write the brief `text` of the row `name` jbus files from the nightly's red run `number`,
    queue it, and say so in a retro line that ends `said`. False where the queue refused it."""
    (run.home / "tasks").mkdir(parents=True, exist_ok=True)
    (run.home / "tasks" / f"{name}.md").write_text(text)
    try:
        queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)
    except Refused as refused:
        run.condition(name, f"its brief was not queued: {refused}")
        return False
    line = f"retro {name}: {nightly.run} {number} failed on {said}"
    run.find(name, "retro", line, key=f"{nightly.file} {number} {name}", past=True)
    return True


def _nightly_runs(run: Pass, nightly: Nightly) -> list[dict[str, Any]] | None:
    """Read a nightly's last 20 completed runs, or nothing where GitHub gave no list. `watch`
    reads every nightly's side by side, before it files from any, since each read is a call to
    GitHub that waits."""
    said = _api(
        run,
        f"repos/{{owner}}/{{repo}}/actions/workflows/{nightly.file}/runs"
        "?status=completed&per_page=20",
    )
    listed = said.get("workflow_runs") if isinstance(said, dict) else None
    return listed if isinstance(listed, list) else None


def _nightly_red(run: Pass, nightly: Nightly, runs: list[dict[str, Any]] | None) -> None:
    """File the brief for the fix of a red run of a nightly workflow, from its completed `runs`
    (`_nightly_runs`, nothing where GitHub gave none), and queue the brief
    unapproved, once per day: a further red run of the day folds into that day's row, whatever its
    state, and files no `-2`. jbus records each run that it has seen in the nightly's `seen`
    file, so it files no brief again for a run whose row was removed. On a project's first
    pass, jbus only records the runs that it sees.

    A red run is one that failed or timed out, and ended within `NIGHTLY_WINDOW`. Where GitHub
    would not give the run's jobs, or a failed job's log, the next pass asks about the run
    again. Once the run ended `NIGHTLY_GRACE` ago, jbus files the brief without the test
    names. jbus files nothing for a pull request's run, nor for a manual run on a branch other
    than the default, and marks it seen: that run is the pull request's or the branch's concern,
    and a red one is no red on main. A release's run, a pushed tag or a published release, is
    filed. A run of macos-nightly.yml is on the default branch whatever it checks
    out, so a nightly with a `title` files only for the runs that carry it.

    The failed shot tests of a run, the kept shots of the view that moved, are not a fix's: they
    file the shots row of the day, `shots-<day>`, whose pull request keeps the shots that run drew
    (`shots.brief`). The rest of the run's failures file the fix's row. `seen` maps a run whose
    only failures were shots to nothing, so jmerge holds no pull request on that red of main
    (`jmerge.rows.browser_fixing`).

    A nightly with a `branch` files a row only for a red run after a run that passed: jbus keeps
    each run that passed as `GREEN` in `seen`, since GitHub lists only the last 20. A red run
    before any is one quiet line, under the workflow's name, and no row asks the user anything.
    """
    if runs is None:
        return
    seen: dict[str, str] = read_json(run.state / nightly.seen, {})
    default = _default_branch(run)
    green = GREEN in seen.values()
    for one in sorted(runs, key=lambda r: r.get("created_at") or ""):
        number = str(one.get("id"))
        ended = when(one.get("updated_at") or one["created_at"])
        stale = run.now - ended > NIGHTLY_WINDOW
        event, off = one.get("event"), one.get("head_branch") != default
        theirs = not nightly.events or event in nightly.events
        if event == "pull_request" or not theirs or (off and event not in NIGHTLY_RELEASE):
            seen.setdefault(number, "")
            continue
        if nightly.title and one.get("display_title") != nightly.title:
            continue
        if nightly.branch and one.get("conclusion") == "success":
            green, seen[number] = True, GREEN
            continue
        if number in seen or one.get("conclusion") not in NIGHTLY_RED or stale:
            continue
        day = run.user.day(when(one["created_at"]))
        if nightly.branch and not green:
            line = (
                f"retro {nightly.file.removesuffix('.yml')}: {nightly.run} {number} failed on "
                f"{day}, and no run of it on {nightly.branch} has passed yet, so no row is filed"
            )
            run.find(nightly.file.removesuffix(".yml"), "retro", line, key=number, past=True)
            seen[number] = ""
            continue
        if run.first:
            seen[number] = ""
            continue
        name, redrawn = f"{nightly.prefix}{day}", f"{shots.PREFIX}{day}"
        free = [
            n for n in (name, redrawn) if n not in run.removed and queue.fresh(run.state, n) is None
        ]
        fixed = name
        if free:
            asked = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs/{number}/jobs?per_page=100")
            if not isinstance(asked, dict):
                if run.now - ended < NIGHTLY_GRACE:
                    continue
                asked = {}
            red = [
                j
                for j in asked.get("jobs") or []
                if j.get("status") == "completed" and j.get("conclusion") not in NOT_RED
            ]
            logs = [job_log(run, "{owner}/{repo}", j.get("id")) for j in red]
            if None in logs and run.now - ended < NIGHTLY_GRACE:
                continue
            jobs = [
                (j.get("name") or "?", j.get("html_url") or "", failed_in(log or ""))
                for j, log in zip(red, logs, strict=True)
            ]
            said = [plain(log or "") for log in logs]
            drawn, rest = drawn_apart(jobs, said)
            fixed = name if rest or not drawn else ""
            if drawn and redrawn in free:
                moved = any(shots.BROWSER_MOVED in log for log in said)
                text = shots.brief(
                    redrawn, day, nightly.run, number, queue.RED_DECIDED, drawn, ran_at(one), moved
                )
                if not _filed(run, nightly, redrawn, text, number, f"{day}, {shots.said(drawn)}"):
                    continue
            if fixed and name in free:
                text = fix_brief(
                    f"{name}: {nightly.failed} on {day}",
                    f'"{nightly.run} {number} failed on {day}, {tests_said(rest)}" '
                    f"(jbus, from {nightly.file})",
                    [
                        f"- {nightly.done}",
                        "- the Result names the cause: the merge that broke it, or a flake with "
                        "its evidence",
                    ],
                    nightly.proves,
                    nightly.filed,
                    [(job, url, failed.tests) for job, url, failed in rest],
                    [ran_at(one)],
                    nowhere=nightly.where,
                    pull=nightly.pull,
                    home=nightly.home,
                )
                if not _filed(run, nightly, name, text, number, f"{day}, {tests_said(rest)}"):
                    continue
        seen[number] = fixed
        write_json(run.state / nightly.seen, seen)
    write_json(run.state / nightly.seen, seen)


def _withdraw(run: Pass, fixes: list[dict[str, Any]], green: str) -> None:
    """Withdraw each fix row filed for a red (its slug ends in the red's commit) that main's tip,
    `green`, has since passed: a fix for a problem already gone is no decision. A row that never
    launched is taken out (`queue.withdraw`), with why in its record. A row that launched is left
    to its crew and its pull request, since its fix may still be needed for a test that turned green
    by chance, and the home hears of it once. The line that says a row is withdrawn is sent once the
    row is out, and a withdrawn row is never one of `fixes` again. A row filed for `green` itself,
    whose check passed on a rerun, is left as it is, and the
    home hears of that once too. A row with a launch record (`jbus.launches`) is left for the pass
    that reads T3 Code's answer."""
    for row in fixes:
        name = row["slug"]
        if green.startswith(name.rsplit("-", 1)[-1]):
            line = f"retro {name}: main is green again at {green[:12]}, and its row is left"
            line += " as it is"
            run.find(name, "retro", line, key=f"green {name}", past=True)
            continue
        if row.get("thread") or row.get("status") not in queue.UNLAUNCHED:
            line = (
                f"retro {name}: main is green again at {green[:12]}, and its row launched, so "
                "it is left to its crew and its pull request"
            )
            run.find(name, "retro", line, key=f"launched {name}", past=True)
            continue
        if records(run, name):
            continue
        why = f"main is green at {green[:12]}, a later commit than the red it was filed for"
        try:
            said = queue.withdraw(run.state, name, why, run.user.stamp(run.now))
        except (Refused, queue.Unparsable) as refused:
            run.condition(name, f"its row was not withdrawn: {refused}")
            continue
        line = f"retro {name}: main is green again at {green[:12]}, and its row is withdrawn"
        run.box.send(name, "retro", line)
        run.box.send(name, "queue", f"queue {run.project.name}: {said}", queue.render([row]))
        run.say(said)


@dataclass(frozen=True)
class RedTip:
    """Main's tip, red after its one rerun, as `retro` read it for `jbus.culprits.judge`, which
    reverts its one clear culprit or files its fix row (`_file`): the slug its row is filed after,
    the tip, the merges since the last green, newest first, the pull request merged at the oldest
    of them and its slug, and the green commit under the oldest, or nothing where none is in
    reach. The oldest is the first red after the last green, so its merge is the one that turned
    main red."""

    slug: str
    sha: str
    red: list[dict]
    pull: dict[str, Any] | None
    culprit: str
    under: str = ""


def retro(run: Pass, world: World, rows: list[dict[str, Any]], check: Callable[[str], str]) -> None:
    """Report a red main within a day of a merge, and a revert of one. Both lines name the
    merged slug. A red tip of main with no briefed merge in the day before it is reported too,
    under the name of its fix row.

    `retro` judges no commit of its own: `mainmoved`, whose `tell` runs before it in a pass, is
    the one judge. Main's tip is red where `main.json` names it red, and green where `main.json`
    names it green, so `retro` and every reader of `main.json` give one verdict for one tip. An
    older commit is judged by `check`, which is `mainmoved.main_check`, the one writer of
    `checks.json`. A main whose run was cancelled is not red: `mainmoved` asks for its run
    again, and `retro` reports only a second cancelled run, or a run GitHub would not start
    again. It reports a red main once for each commit. A merge into another branch than main, a
    merge base's, did not land on main, so it takes no blame for it. `retro` files and queues a
    brief for the fix once, and only for main's tip as this pass reads it: it hands the tip, with
    every commit since the last green, to `jbus.culprits.judge` as `Pass.red`, which reverts its
    one clear culprit, the merge at the first red after that green, or files its row (`_file`).
    A red commit that a later commit superseded is no longer main, so there is nothing to fix.
    Once main's tip is green at a later commit than the one a fix row was filed for, the red is
    gone: `_withdraw` takes out a row that never launched, and reports once a
    row that did, which its crew and pull request keep. With no briefed merge and no open fix
    row, `retro` asks GitHub nothing until `main.json` keeps a red tip.
    """
    slugs = sorted(
        (s for s in world.merged if brief_of(run, s) and s not in run.gated),
        key=lambda s: world.merged[s]["mergedAt"],
    )
    fixes = [
        row for row in rows if mainjson.fix_of(row["slug"]) and row.get("status") not in queue.FINAL
    ]
    main = mainjson.read(run.state)
    if not slugs and not fixes and not main.red:
        return
    branch = _default_branch(run)
    merges = [
        world.merged[slug]
        for slug in slugs
        if world.merged[slug].get("baseRefName", branch) in (branch, None, "")
    ]
    slug_of = {pull["number"]: slug for slug, pull in world.merged.items()}
    commits = main_commits(run)
    if not isinstance(commits, list):
        return
    tip = commits[0]["sha"] if commits else ""
    if fixes and tip and main.green == tip:
        _withdraw(run, fixes, tip)
    by_commit = {(p.get("mergeCommit") or {}).get("oid"): p for p in merges}
    for place, commit in enumerate(commits):
        sha, message = commit["sha"], commit["commit"]["message"]
        for pull in merges:
            merge = (pull.get("mergeCommit") or {}).get("oid") or ""
            named = bool(merge) and (merge in message or merge[:12] in message)
            if sha != merge and (named or f'Revert "{pull["title"]}' in message):
                slug = slug_of[pull["number"]]
                line = f"retro {slug}: reverted by {sha[:12]}"
                run.find(slug, "retro", line, key=f"revert {sha}", past=True)
        date = when(commit["commit"]["committer"]["date"])
        before = [p for p in merges if timedelta(0) <= date - when(p["mergedAt"]) <= RETRO]
        pull = by_commit.get(sha) or (before[-1] if before else None)
        if pull is None or run.now - date > RETRO:
            pull = None
            if place != 0:
                continue
        slug = slug_of[pull["number"]] if pull else ""
        if place != 0:
            answer = check(sha)
        elif sha == main.red:
            answer = "failed"
        else:
            kept = read_json(run.state / "checks.json", {}).get(sha, "pending")
            answer = "pending" if kept == "failed" else kept
        if slug and answer in ("cancelled", "refused"):
            twice = f"main check cancelled twice at {sha[:12]}"
            unasked = f"main check cancelled at {sha[:12]}, and GitHub did not run it again"
            line = f"retro {slug}: {twice if answer == 'cancelled' else unasked}"
            run.find(slug, "retro", line, key=f"cancelled {sha}", past=True)
        if answer != "failed":
            continue
        since, under = 1, ""
        for older in commits[place + 1 : place + 20]:
            if older["sha"] == main.green or check(older["sha"]) == "green":
                under = older["sha"]
                break
            since += 1
        owner = slug or f"{mainjson.FIX}{sha[:12]}"
        line = (
            f"retro {owner}: main check failed at {sha[:12]}, {since} merges since the last green"
        )
        line += "" if slug else ", and no briefed merge came in the day before it"
        run.find(owner, "retro", line, key=f"red {sha}", past=True)
        if place == 0:
            red = commits[place : place + since]
            pull = by_commit.get(red[-1]["sha"])
            culprit = slug_of.get(pull["number"], "") if pull else ""
            run.red = RedTip(slug, sha, red, pull, culprit, under)


STEPS = (
    verbs.Step(
        "tellers",
        40,
        "watch.watch",
        lambda half: watch(half.run, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
    verbs.Step(
        "tellers",
        41,
        "watch.rewritten",
        lambda half: rewritten(half.run, half.client, half.rows),
        ("sight", "client"),
    ),
)
