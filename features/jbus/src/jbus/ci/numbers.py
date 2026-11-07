"""Count the nine targets of the CI plan, and the six CI health numbers, from what `jbus ci` kept
(`jbus.ci.ledger`).

Each number counts over a window of time and says how it counts: `Number.how` is the
sentence shown with it on the panel and in the weekly report. Every number follows these
rules:

- The period is the window, from `start` up to `end`. A job belongs to the day its `created`
  falls in, a pull request to the day it merged, and a push to main to the day it completed.
- It counts jobs, never runs: a `check` job and a `full` job each count once.
- It counts the jobs that ran, on a self-hosted (`local`) runner or a GitHub-hosted one, together.
  `Number.runners` says which runners a number covers, and how many jobs of each.
- It counts a job cancelled while it waited. That job got no minute of execution, so it is in
  the jobs of the queue and not in the minutes of execution.

The nine, in order:

1. `queue`: the median minutes a green job waited (`created` to `started`), against the
   median minutes it ran. The target is that the wait is under the run.
2. `waste`: the share of execution minutes spent by jobs that failed or were cancelled.
   The target is under 15%.
3. `own`: of the jobs that failed on their last attempt, the share whose cause is the pull
   request's own. The target is over 70%. A red job's cause is `main` when main was red with the
   same failing tests at the time the job started. It is `runner` when its log shows a runner fault
   and another branch fails the same tests, and `flake` when no fault shows. Otherwise it is `own`.
4. `rebases`: force-pushes per pull request merged. The target is under 0.3.
5. `stale`: the force-pushes made only because main had moved, as the jbus event before each
   one shows. The target is none.
6. `green`: the median minutes from the first job on a merged pull request's final head to
   the last green one. The target is under 15 (set here; the scout named none).
7. `mainred`: the minutes main was red, on the window's last day, from the first failed push
   to main until the next green one. The target is under 30 (set here).
8. `flaky`: the tests that failed on two branches in the window with no fault in the log.
   The target is under 3 (set here). The scout counted 9 by hand; this number follows the rule.
9. `inode`: the peak of /tmp's inode use a job wrote with `jbus ci --notice` (`tmp_inode_pct`).
   The target is under 80 (set here). It has no value until a job writes it.

The six health numbers (`HEALTH`) follow, as cicd-metrics-scout defined them on 2026-11-04:
`red_share`, `shas_per_pr`, `wait_p90_shard`, `wait_p90_macos`, `open_to_merge` and
`first_check_own_red`, each with its rule in its `how`. They are a baseline: none is held to a
target yet, so each has `met` None and none raises an alert. The scout's goals, for 50 pull requests
opened after the verify-trust moves, are in their `target`.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from functools import cached_property
from typing import Any

import jsettings
from jbus.ci import macjobs
from jbus.watch import mac_job

LOOKBACK = timedelta(hours=2)
FALLBACK = timedelta(hours=24)
KINDS = ("rebase", "conflict", "mainmoved", "failed", "refailed", "expedite", "review")
FIX = {"failed", "refailed", "expedite", "review", "resume"}
CONFLICT = {"rebase-conflict", "conflict", "rebase-fresh-fails"}
STALE = {"rebase-main-changed", "rebase-fresh-timeout", "mainmoved-prev-green"}
TARGETS = {
    "queue": ("queue p50 under exec p50", "queue under exec"),
    "waste": ("wasted-minute share", "under 15%"),
    "own": ("own-cause reds", "over 70%"),
    "rebases": ("rebases per merged PR", "under 0.3"),
    "stale": ("staleness-only rebases", "none"),
    "green": ("time-to-green p50", "under 15 min"),
    "mainred": ("main-red minutes per day", "under 30 min"),
    "flaky": ("flaky tests", "under 3"),
    "inode": ("/tmp inode peak", "under 80%"),
    "red_share": ("red share of active PRs", "baseline"),
    "shas_per_pr": ("shas per merged PR", "baseline, goal crew 1.5"),
    "wait_p90_shard": ("shard queue wait p90", "baseline"),
    "wait_p90_macos": ("macos queue wait p90", "baseline"),
    "open_to_merge": ("open to merge p50", "baseline"),
    "first_check_own_red": ("first-check own red", "baseline, goal 15%"),
}
CHECK = "check"
"""The job of check.yml that passes only when the pull request's check passed."""
SHARD = re.compile(r"check \d+ of \d+")
ASKED = re.compile(r"\w+ (\d+) \S+: GitHub was asked to merge ")
"""jmerge's line when it asked GitHub to merge the base into a pull request's branch."""
ASK_LAG = timedelta(minutes=2)
"""How long after GitHub made the merge jmerge may log its ask: it logs once the call returned."""
ASK_LEAD = timedelta(minutes=10)
"""How long before the merge's first job jmerge may have asked for it."""
OPENED, MERGED = timedelta(minutes=5), timedelta(minutes=2)
"""How far before its opening and after its merge a pull request's run still counts as its own."""
OWN = {"own", "unread"}
RAN = {"success", "failure", "cancelled"}
PULLS = "pull requests, any runner"
"""What `Number.runners` says of a target that counts pull requests and not jobs."""


@dataclass(frozen=True)
class Number:
    """A `Number` is one target. It has its `value`, `shown` (how the value reads), the `target`
    it is checked against, and `met` (None where there was nothing to count). It also has `n`,
    the jobs or pull requests counted, `how` it counts, and `runners`, the runners its jobs ran
    on with how many of each (`local 3, hosted 40`), or `PULLS`."""

    key: str
    name: str
    value: float | None
    shown: str
    target: str
    met: bool | None
    n: int
    how: str
    runners: str = ""


def time(text: str | None) -> datetime | None:
    return jsettings.when(text) if text else None


def minutes(first: str | None, last: str | None) -> float:
    a, b = time(first), time(last)
    return (b - a).total_seconds() / 60 if a and b else 0.0


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * share
    low = int(at)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _runners(jobs: list[dict[str, Any]]) -> str:
    kinds = Counter(j["kind"] for j in jobs)
    return ", ".join(f"{kind} {kinds[kind]}" for kind in ("local", "hosted") if kinds[kind])


def _text(value: float, places: int = 1) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".")


def _number(
    key: str,
    value: float | None,
    shown: str,
    met: bool | None,
    n: int,
    how: str,
    runners: str = "",
) -> Number:
    name, target = TARGETS[key]
    return Number(
        key, name, value, shown if value is not None else "no data", target, met, n, how, runners
    )


def _of_main(job: dict[str, Any]) -> bool:
    """Return whether a job is one of main's check: a push to main, not one of macos.yml, which
    `jbus.watch` never judges as main's check."""
    return job["event"] == "push" and job["branch"] == "main" and not mac_job(job.get("name"))


def _ran(job: dict[str, Any]) -> bool:
    return bool(job.get("runner") and job.get("started") and job.get("completed")) and (
        job.get("conclusion") != "skipped"
    )


def _in(stamp: str | None, start: datetime, end: datetime) -> bool:
    moment = time(stamp)
    return moment is not None and start <= moment < end


class Facts:
    """`Facts` reads the ledger once and works out these facts from it, once each: the pull request
    each jbus event is about, the runs of main in order, the intervals main was red, the cause
    of each red, and the cause of each force-push."""

    def __init__(
        self,
        jobs: list[dict[str, Any]],
        pulls: list[dict[str, Any]],
        events: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        self.jobs, self.pulls, self.events, self.now = jobs, pulls, events, now
        self.main = self._main()
        self.intervals = self._intervals()
        self.causes = self._causes()
        self.pushes = self._pushes()

    def _main(self) -> list[tuple[datetime, str, str, datetime]]:
        """Return each run of main that ran, as (created, sha, state, completed), oldest first."""
        runs: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for job in self.jobs:
            if (
                _of_main(job)
                and job.get("steps")
                and job["conclusion"] in ("success", "failure")
                and job.get("created")
                and job.get("completed")
            ):
                runs[job["run"]].append(job)
        found = []
        for run in runs.values():
            state = "failure" if any(j["conclusion"] == "failure" for j in run) else "success"
            found.append(
                (
                    min(jsettings.when(j["created"]) for j in run),
                    run[0]["sha"],
                    state,
                    max(jsettings.when(j["completed"]) for j in run),
                )
            )
        return sorted(found)

    def _intervals(self) -> list[tuple[datetime, datetime]]:
        """Return the times main was red: from the first failed run to the next green one."""
        found, red = [], None
        for _, _, state, done in sorted(self.main, key=lambda one: one[3]):
            if state == "failure" and red is None:
                red = done
            elif state == "success" and red is not None:
                found.append((red, done))
                red = None
        if red is not None:
            found.append((red, self.now))
        return found

    def _branch(self, job: dict[str, Any]) -> str:
        if job["branch"] != "main":
            return job["branch"]
        for one in self.pulls:
            if one.get("merge_commit") and one["merge_commit"] == job["sha"]:
                return one["branch"]
        return "main"

    def _red_until(self, job: dict[str, Any]) -> datetime | None:
        done = time(job["completed"])
        for start, end in self.intervals:
            if done and start <= done <= end:
                return end
        return None

    def _inherited(self, job: dict[str, Any], mains: list[dict[str, Any]]) -> bool:
        ids, began = set(job["tests"] or []), time(job["started"] or job["created"])
        for one in mains:
            until, at = self._red_until(one), time(one["started"] or one["created"])
            if (
                until
                and began
                and at is not None
                and at < began
                and ids & set(one["tests"] or [])
                and began < until
            ):
                return True
        return False

    def _causes(self) -> dict[int, str]:
        """Return the cause of each failed job: `main`, `runner`, `flake` or `own`."""
        failed = [j for j in self.jobs if j["conclusion"] == "failure"]
        mains = [j for j in failed if j["branch"] == "main" and j["event"] == "push" and j["tests"]]
        inherited = {j["job"]: self._inherited(j, mains) for j in failed}
        found: dict[int, str] = {}
        for job in failed:
            ids = set(job["tests"] or [])
            if job["tests"] is None:
                found[job["job"]] = "unread"
                continue
            if inherited[job["job"]]:
                found[job["job"]] = "main"
                continue
            elsewhere = {
                self._branch(other)
                for other in failed
                if other is not job
                and ids & set(other["tests"] or [])
                and self._branch(other) != self._branch(job)
                and not inherited[other["job"]]
            }
            if ids and elsewhere:
                found[job["job"]] = "runner" if job["signs"] else "flake"
            else:
                found[job["job"]] = "own"
        return found

    def _pull_of(self, event: dict[str, Any]) -> int | None:
        named = re.search(r"#(\d+)", event.get("line", ""))
        if named:
            return int(named[1])
        for one in self.pulls:
            if one["branch"] == event.get("slug"):
                return int(one["number"])
        return None

    def _state_before(self, sha: str) -> str:
        for at, (_, head, _, _) in enumerate(self.main):
            if head.startswith(sha):
                return self.main[at - 1][2] if at else "unknown"
        return "unknown"

    def _messages(self) -> dict[int, list[tuple[datetime, str]]]:
        found: dict[int, list[tuple[datetime, str]]] = defaultdict(list)
        for event in self.events:
            kind, said = event.get("event", ""), event.get("text", "")
            number, at = self._pull_of(event), time(event.get("at"))
            if kind not in (*KINDS, "resume", "rereview", "drops") or number is None or at is None:
                continue
            if kind == "review" and "Verdict: findings" not in said:
                continue
            if kind == "expedite" and not re.search(r"short of \((unfixed|fix)", event["line"]):
                continue
            if kind == "rebase":
                label = (
                    "rebase-conflict"
                    if "conflicts with its base" in said
                    else "rebase-main-changed"
                    if "needs a fresh check" in said
                    else "rebase-fresh-timeout"
                    if "timed out" in said
                    else "rebase-fresh-fails"
                    if "fails on" in said
                    else "rebase-other"
                )
            elif kind == "mainmoved":
                sha = re.search(r"main ([0-9a-f]{7,})", event["line"])
                label = "mainmoved-prev-" + (
                    {"success": "green", "failure": "red"}.get(
                        self._state_before(sha[1]), "unknown"
                    )
                    if sha
                    else "unknown"
                )
            else:
                label = kind
            found[number].append((at, label))
        return found

    def _pushes(self) -> list[tuple[int, datetime, str]]:
        """Return each force-push of a pull request's branch, with its cause: `conflict` (the
        rebase resolved a conflict), `staleness` (main had only moved), `fix` or `unknown`."""
        messages = self._messages()
        found = []
        for one in self.pulls:
            number = int(one["number"])
            ordered = sorted(jsettings.when(x) for x in one.get("pushes", []))
            for at, pushed in enumerate(ordered):
                near = [m for m in messages[number] if pushed - LOOKBACK <= m[0] <= pushed]
                rebased = [m for m in near if m[1].startswith(("rebase", "conflict", "mainmoved"))]
                fixed = [m for m in near if m[1] in FIX]
                trigger = max(rebased)[1] if rebased else (max(fixed)[1] if fixed else None)
                if trigger is None:
                    since = max(pushed - FALLBACK, ordered[at - 1] if at else pushed - FALLBACK)
                    late = [
                        m
                        for m in messages[number]
                        if since <= m[0] <= pushed
                        and m[1].startswith(("rebase", "conflict", "mainmoved"))
                    ]
                    trigger = max(late)[1] if late else None
                if trigger in CONFLICT:
                    cause = "conflict"
                elif trigger in STALE:
                    cause = "staleness"
                elif trigger is not None and not trigger.startswith(
                    ("rebase", "mainmoved-prev-unknown")
                ):
                    cause = "fix"
                else:
                    cause = "unknown"
                found.append((number, pushed, cause))
        return found

    @cached_property
    def attempts(self) -> dict[tuple[int, int], list[dict[str, Any]]]:
        found: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for job in self.jobs:
            found[(job["run"], job["attempt"])].append(job)
        return found

    @cached_property
    def checks(self) -> list[dict[str, Any]]:
        """Return the completed `check` jobs of pull requests, oldest first."""
        return sorted(
            (
                j
                for j in self.jobs
                if j["name"] == CHECK
                and j["event"] == "pull_request"
                and j.get("pr") is not None
                and j["conclusion"] in ("success", "failure")
            ),
            key=lambda j: jsettings.when(j["created"]),
        )

    def own_red(self, check: dict[str, Any]) -> bool:
        """Whether a red `check` was red for a cause of the pull request's own."""
        causes = {
            self.causes[j["job"]]
            for j in self.attempts[(check["run"], check["attempt"])]
            if j["conclusion"] == "failure" and j["name"] != CHECK
        }
        return not causes or bool(causes & OWN)

    @cached_property
    def heads(self) -> dict[int, list[tuple[datetime, str, str]]]:
        """Return the heads check.yml ran on for each pull request, oldest first, as (its first
        job's `created`, sha, kind), between its opening and its merge. A run skipped whole ran on
        no head. The kind is `update` where jmerge asked GitHub to merge the base into the branch
        just before the head's first job (`ASK_LEAD`), or just after it (`ASK_LAG`), and after the
        head before it, and `crew` otherwise."""
        runs: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for job in self.jobs:
            if job["event"] == "pull_request" and job.get("pr") is not None:
                runs[job["run"]].append(job)
        lives = {
            int(p["number"]): (
                jsettings.when(p["created"]) - OPENED,
                jsettings.when(p["merged"]) + MERGED if p.get("merged") else self.now,
            )
            for p in self.pulls
            if p.get("created")
        }
        first: dict[int, dict[str, datetime]] = defaultdict(dict)
        for run in runs.values():
            number = int(run[0]["pr"])
            ran = any(j["conclusion"] in RAN for j in run)
            if number not in lives or not ran or not any(j["name"] == CHECK for j in run):
                continue
            at, sha = min(jsettings.when(j["created"]) for j in run), run[0]["sha"]
            opened, closed = lives[number]
            if opened <= at <= closed and at < first[number].get(sha, closed + MERGED):
                first[number][sha] = at
        asks: dict[int, list[datetime]] = defaultdict(list)
        for event in self.events:
            named = ASKED.match(event.get("line", "")) if event.get("event") == "jmerge" else None
            if named and event.get("at"):
                asks[int(named[1])].append(jsettings.when(event["at"]))
        found: dict[int, list[tuple[datetime, str, str]]] = {}
        for number, shas in first.items():
            ordered, before = [], None
            for sha, at in sorted(shas.items(), key=lambda one: one[1]):
                asked = any(
                    (before is None or ask > before + ASK_LAG)
                    and at - ASK_LEAD <= ask <= at + ASK_LAG
                    for ask in asks[number]
                )
                ordered.append((at, sha, "update" if asked else "crew"))
                before = at
            found[number] = ordered
        return found


def queue(facts: Facts, start: datetime, end: datetime) -> Number:
    green = [
        j
        for j in facts.jobs
        if _ran(j) and j["conclusion"] == "success" and _in(j["created"], start, end)
    ]
    how = (
        "median minutes a green job waited for a runner against the median it ran, job level; "
        "a job cancelled while it waited is in neither (it never ran)"
    )
    if not green:
        return _number("queue", None, "", None, 0, how)
    wait = percentile([minutes(j["created"], j["started"]) for j in green], 0.5)
    run = percentile([minutes(j["started"], j["completed"]) for j in green], 0.5)
    shown = f"{_text(wait)} vs {_text(run, 2)} min"
    return _number("queue", wait, shown, wait < run, len(green), how, _runners(green))


def waste(facts: Facts, start: datetime, end: datetime) -> Number:
    ran = [j for j in facts.jobs if _ran(j) and _in(j["created"], start, end)]
    lost = sum(
        minutes(j["started"], j["completed"])
        for j in ran
        if j["conclusion"] in ("failure", "cancelled")
    )
    total = sum(minutes(j["started"], j["completed"]) for j in ran)
    how = (
        "execution minutes of jobs that failed or were cancelled over all execution minutes, "
        "job level; a job cancelled while it waited has none to count"
    )
    if not total:
        return _number("waste", None, "", None, 0, how)
    share = lost / total
    return _number("waste", share, f"{share:.1%}", share < 0.15, len(ran), how, _runners(ran))


def _final(facts: Facts) -> set[int]:
    last: dict[int, int] = {}
    for job in facts.jobs:
        last[job["run"]] = max(last.get(job["run"], 0), job["attempt"])
    return {j["job"] for j in facts.jobs if j["attempt"] == last[j["run"]]}


def own(facts: Facts, start: datetime, end: datetime) -> Number:
    final = _final(facts)
    reds = [
        j
        for j in facts.jobs
        if j["conclusion"] == "failure"
        and j["job"] in final
        and _in(j["started"] or j["created"], start, end)
    ]
    counted = [facts.causes[j["job"]] for j in reds]
    split = ", ".join(
        f"{counted.count(c)} {c}"
        for c in ("own", "main", "runner", "flake", "unread")
        if c in counted
    )
    how = (
        "failed jobs, last attempt of a run, that were the pull request's "
        "own fault: not main already red with the same tests, a runner fault, or a flake "
        "(the same tests red on another branch). A job whose log could not be read is counted "
        "and is not the pull request's"
    )
    if not reds:
        return _number("own", None, "", None, 0, how)
    share = counted.count("own") / len(counted)
    return _number(
        "own",
        share,
        f"{share:.0%} ({counted.count('own')} of {len(counted)}: {split})",
        share > 0.7,
        len(counted),
        how,
        _runners(reds),
    )


def _merged(facts: Facts, start: datetime, end: datetime) -> list[dict[str, Any]]:
    return [p for p in facts.pulls if _in(p.get("merged"), start, end)]


def rebases(facts: Facts, start: datetime, end: datetime) -> Number:
    merged = _merged(facts, start, end)
    how = (
        "force-pushes of the branches of the pull requests merged in the period, over those "
        "pull requests"
    )
    if not merged:
        return _number("rebases", None, "", None, 0, how)
    pushes = sum(len(p.get("pushes", [])) for p in merged)
    value = pushes / len(merged)
    return _number(
        "rebases",
        value,
        f"{value:.2f} ({pushes} over {len(merged)})",
        value < 0.3,
        len(merged),
        how,
        PULLS,
    )


def stale(facts: Facts, start: datetime, end: datetime) -> Number:
    found = [x for x in facts.pushes if x[2] == "staleness" and start <= x[1] < end]
    counted = [x for x in facts.pushes if start <= x[1] < end]
    how = (
        "force-pushes in the period whose cause was only that main had moved, read from the "
        "jbus event before the push (a rebase of a fresh check, a main that moved while green); "
        "of the pushes in the period"
    )
    if not counted:
        return _number("stale", None, "", None, 0, how)
    shown = f"{len(found)} of {len(counted)}"
    return _number("stale", float(len(found)), shown, not found, len(counted), how, PULLS)


def green(facts: Facts, start: datetime, end: datetime) -> Number:
    found, counted = [], []
    for one in _merged(facts, start, end):
        ran = [j for j in facts.jobs if j["sha"] == one["head"] and j["event"] == "pull_request"]
        ok = [j for j in ran if j["conclusion"] == "success"]
        if ok:
            found.append(minutes(min(j["created"] for j in ran), max(j["completed"] for j in ok)))
            counted += [j for j in ran if _ran(j)]
    how = (
        "minutes from the first job on a merged pull request's final head to the last green "
        "one, median over the pull requests merged in the period"
    )
    if not found:
        return _number("green", None, "", None, 0, how)
    value = percentile(found, 0.5)
    shown = f"{_text(value)} min"
    return _number("green", value, shown, value < 15, len(found), how, _runners(counted))


def mainred(facts: Facts, start: datetime, end: datetime) -> Number:
    spent = sum(
        max(0.0, (min(b, end) - max(a, start)).total_seconds() / 60) for a, b in facts.intervals
    )
    days = max((end - start) / timedelta(days=1), 1.0)
    value = spent / days
    how = (
        "minutes main was red, from the first failed run of a push to main to the next green "
        "one, per day of the period (a day not yet over counts as a whole one); a run that "
        "never ran a step is not counted"
    )
    seen = sum(1 for one in facts.main if one[0] < end)
    if not seen:
        return _number("mainred", None, "", None, 0, how)
    ran = [
        j for j in facts.jobs if _of_main(j) and j.get("steps") and _in(j["created"], start, end)
    ]
    shown = f"{_text(value)} min"
    return _number("mainred", value, shown, value < 30, seen, how, _runners(ran))


def flake_branches(facts: Facts, start: datetime, end: datetime) -> dict[str, set[str]]:
    """Return each test that failed in a flake job of the period, with the branches it failed on.
    A flake job may hold a test that failed on its branch alone: the test is a flake only where
    it failed on two branches."""
    found: dict[str, set[str]] = defaultdict(set)
    for job in facts.jobs:
        if (
            job["conclusion"] == "failure"
            and facts.causes[job["job"]] == "flake"
            and _in(job["created"], start, end)
        ):
            for test in job["tests"]:
                found[test].add(facts._branch(job))
    return found


def flaky(facts: Facts, start: datetime, end: datetime) -> Number:
    red = [j for j in facts.jobs if j["conclusion"] == "failure" and _in(j["created"], start, end)]
    ids = {test for test, where in flake_branches(facts, start, end).items() if len(where) > 1}
    how = (
        "tests that failed on two branches in the period with no runner fault in the log and "
        "no red main to blame; counted by this rule, not by hand"
    )
    if not red:
        return _number("flaky", None, "", None, 0, how)
    shown = str(len(ids))
    return _number("flaky", float(len(ids)), shown, len(ids) < 3, len(red), how, _runners(red))


def inode(facts: Facts, start: datetime, end: datetime) -> Number:
    wrote = [
        j
        for j in facts.jobs
        if j.get("tmp_inode_pct") is not None and _in(j["created"], start, end)
    ]
    how = "the highest /tmp inode use a job wrote with `jbus ci --notice`"
    if not wrote:
        return _number("inode", None, "", None, 0, how)
    peak = max(float(j["tmp_inode_pct"]) for j in wrote)
    return _number("inode", peak, f"{_text(peak)}%", peak < 80, len(wrote), how, _runners(wrote))


def red_share(facts: Facts, start: datetime, end: datetime) -> Number:
    active: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for job in facts.checks:
        if _in(job["created"], start, end):
            active[job["pr"]].append(job)
    how = (
        "of the pull requests with a completed `check` job created in the period, the share with "
        "a red one, any attempt. A red pull request is own where a red check failed a job of its "
        "own cause or one whose log was not read (`own`'s rule), or no job but `check`, and shared "
        "where each failed job was main's, a runner's or a flake"
    )
    if not active:
        return _number("red_share", None, "", None, 0, how)
    red = [jobs for jobs in active.values() if any(j["conclusion"] == "failure" for j in jobs)]
    own = sum(any(facts.own_red(j) for j in jobs if j["conclusion"] == "failure") for jobs in red)
    n, counted = len(active), [j for jobs in active.values() for j in jobs]
    shown = f"{len(red) / n:.0%} ({len(red)} of {n}: {own} own, {len(red) - own} shared)"
    return _number("red_share", len(red) / n, shown, None, n, how, _runners(counted))


def shas_per_pr(facts: Facts, start: datetime, end: datetime) -> Number:
    merged = _merged(facts, start, end)
    how = (
        "heads check.yml ran on (a run skipped whole is none) in the life of each pull request "
        "merged in the period, over those pull requests. A head is an update where jmerge had just "
        "asked GitHub to merge main into the branch (`Facts.heads`), and the crew's otherwise; the "
        "value is the crew's"
    )
    if not merged:
        return _number("shas_per_pr", None, "", None, 0, how)
    kinds = Counter(kind for p in merged for _, _, kind in facts.heads.get(int(p["number"]), []))
    crew, update = kinds["crew"] / len(merged), kinds["update"] / len(merged)
    shown = f"{crew:.2f} crew + {update:.2f} update = {crew + update:.2f} ({len(merged)} merged)"
    return _number("shas_per_pr", crew, shown, None, len(merged), how, PULLS)


def _wait(key: str, facts: Facts, start: datetime, end: datetime, jobs: str) -> Number:
    mac = macjobs.on_mac(facts.jobs)
    waited = [
        j
        for j in facts.jobs
        if j["event"] == "pull_request"
        and j.get("started")
        and (SHARD.fullmatch(j["name"]) if key == "wait_p90_shard" else mac(j))
        and _in(j["created"], start, end)
    ]
    how = (
        f"the 90th percentile of the seconds a pull request's {jobs} job waited for a runner "
        "(`created` to `started`), with the median, over the jobs created in the period that "
        "started; a job cancelled while it waited is not counted"
    )
    if not waited:
        return _number(key, None, "", None, 0, how)
    seconds = [minutes(j["created"], j["started"]) * 60 for j in waited]
    high, middle = percentile(seconds, 0.9), percentile(seconds, 0.5)
    shown = f"{high:.0f} s (p50 {middle:.0f} s)"
    return _number(key, high, shown, None, len(waited), how, _runners(waited))


def wait_p90_shard(facts: Facts, start: datetime, end: datetime) -> Number:
    return _wait("wait_p90_shard", facts, start, end, "`check N of M`")


def wait_p90_macos(facts: Facts, start: datetime, end: datetime) -> Number:
    return _wait("wait_p90_macos", facts, start, end, macjobs.NAMED)


def open_to_merge(facts: Facts, start: datetime, end: datetime) -> Number:
    merged = [p for p in _merged(facts, start, end) if p.get("created")]
    how = (
        "hours from a pull request's opening to its merge, median and 90th percentile, over "
        "the pull requests merged in the period"
    )
    if not merged:
        return _number("open_to_merge", None, "", None, 0, how)
    hours = [minutes(p["created"], p["merged"]) / 60 for p in merged]
    middle, high = percentile(hours, 0.5), percentile(hours, 0.9)
    shown = f"{_text(middle)} h p50, {_text(high)} h p90"
    return _number("open_to_merge", middle, shown, None, len(merged), how, PULLS)


def first_check_own_red(facts: Facts, start: datetime, end: datetime) -> Number:
    first: dict[int, dict[str, Any]] = {}
    for job in facts.checks:
        first.setdefault(job["pr"], job)
    counted = [j for j in first.values() if _in(j["created"], start, end)]
    how = (
        "of the pull requests whose first completed `check` job was created in the period, the "
        "share whose first check was red for a cause of its own, by red share's rule"
    )
    if not counted:
        return _number("first_check_own_red", None, "", None, 0, how)
    red, n = [j for j in counted if j["conclusion"] == "failure"], len(counted)
    own = sum(facts.own_red(j) for j in red)
    shown = f"{own / n:.0%} ({own} of {n} first checks, {len(red)} red)"
    return _number("first_check_own_red", own / n, shown, None, n, how, _runners(counted))


ALL: tuple[Callable[[Facts, datetime, datetime], Number], ...] = (
    queue,
    waste,
    own,
    rebases,
    stale,
    green,
    mainred,
    flaky,
    inode,
    red_share,
    shas_per_pr,
    wait_p90_shard,
    wait_p90_macos,
    open_to_merge,
    first_check_own_red,
)
HEALTH = ALL[9:]
"""The six health numbers, which the report also gives day by day."""


def compute(facts: Facts, start: datetime, end: datetime) -> list[Number]:
    """Count the nine targets and the six health numbers over the window from `start` up to
    `end`."""
    return [one(facts, start, end) for one in ALL]


def day_windows(now: datetime, days: int, zone: tzinfo) -> list[tuple[str, datetime, datetime]]:
    """Return the last `days` days in `zone`, oldest first, the last one ending at `now`."""
    today = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    found = []
    for back in range(days - 1, -1, -1):
        first = today - timedelta(days=back)
        last = first + timedelta(days=1)
        found.append(
            (
                first.strftime("%Y-%m-%d"),
                first.astimezone(UTC),
                min(last.astimezone(UTC), now),
            )
        )
    return found
