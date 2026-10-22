"""Count the nine targets of the CI plan from what `jbus ci` kept (`jbus.ci.ledger`).

Each number counts over a window of time and says how it counts: `Number.how` is the
sentence shown with it on the panel and in the weekly report. Every number follows these
rules:

- The period is the window, from `start` up to `end`. A job belongs to the day its `created`
  falls in, a pull request to the day it merged, and a push to main to the day it completed.
- It counts jobs, never runs: a `check` job and a `full` job each count once.
- It counts local and hosted runners apart. `Number.value` is the local runner's figure,
  which the targets are about, and `Number.hosted` is the hosted runner's, where there is one.
- It counts a job cancelled while it waited. That job got no minute of execution, so it is in
  the jobs of the queue and not in the minutes of execution.

The nine, in order:

1. `queue`: the median minutes a green job waited (`created` to `started`), against the
   median minutes it ran. The target is that the wait is under the run.
2. `waste`: the share of execution minutes spent by jobs that failed or were cancelled.
   The target is under 15%.
3. `own`: of the local jobs that failed on their last attempt, the share whose cause is the pull
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
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

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
}


@dataclass(frozen=True)
class Number:
    """A `Number` is one target. It has its `value` (the local runner's figure), `shown`
    (how the value reads), the `target` it is checked against, and `met` (None where there
    was nothing to count). It also has `n`, the jobs or pull requests counted, `how` it
    counts, and `hosted`, the hosted runner's figure."""

    key: str
    name: str
    value: float | None
    shown: str
    target: str
    met: bool | None
    n: int
    how: str
    hosted: str = ""


def time(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def minutes(first: str | None, last: str | None) -> float:
    a, b = time(first), time(last)
    return (b - a).total_seconds() / 60 if a and b else 0.0


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * share
    low = int(at)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _text(value: float, places: int = 1) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".")


def _number(
    key: str,
    value: float | None,
    shown: str,
    met: bool | None,
    n: int,
    how: str,
    hosted: str = "",
) -> Number:
    name, target = TARGETS[key]
    return Number(
        key, name, value, shown if value is not None else "no data", target, met, n, how, hosted
    )


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
                job["event"] == "push"
                and job["branch"] == "main"
                and job.get("steps")
                and job["conclusion"] in ("success", "failure")
            ):
                runs[job["run"]].append(job)
        found = []
        for run in runs.values():
            state = "failure" if any(j["conclusion"] == "failure" for j in run) else "success"
            found.append(
                (
                    min(time(j["created"]) for j in run),
                    run[0]["sha"],
                    state,
                    max(time(j["completed"]) for j in run),
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
            until = self._red_until(one)
            if (
                until
                and began
                and time(one["started"] or one["created"]) < began
                and ids & set(one["tests"] or [])
                and began < until
            ):
                return True
        return False

    def _causes(self) -> dict[int, str]:
        """Return the cause of each failed job: `main`, `runner`, `flake` or `own`."""
        failed = [j for j in self.jobs if j["conclusion"] == "failure"]
        mains = [
            j
            for j in failed
            if j["branch"] == "main"
            and j["event"] == "push"
            and j["kind"] == "local"
            and j["tests"]
        ]
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
            kind, said = event.get("event"), event.get("text", "")
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
            ordered = sorted(time(x) for x in one.get("pushes", []))
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


def queue(facts: Facts, start: datetime, end: datetime) -> Number:
    def of(kind: str) -> tuple[list[float], list[float]]:
        green = [
            j
            for j in facts.jobs
            if j["kind"] == kind
            and _ran(j)
            and j["conclusion"] == "success"
            and _in(j["created"], start, end)
        ]
        return (
            [minutes(j["created"], j["started"]) for j in green],
            [minutes(j["started"], j["completed"]) for j in green],
        )

    waits, runs = of("local")
    h_waits, h_runs = of("hosted")
    how = (
        "median minutes a green job waited for a runner against the median it ran, on the "
        "local runner, job level; a job cancelled while it waited is in neither (it never ran)"
    )
    hosted = (
        f"{_text(percentile(h_waits, 0.5))} vs {_text(percentile(h_runs, 0.5), 2)} min"
        if h_waits
        else ""
    )
    if not waits:
        return _number("queue", None, "", None, 0, how, hosted)
    wait, run = percentile(waits, 0.5), percentile(runs, 0.5)
    shown = f"{_text(wait)} vs {_text(run, 2)} min"
    return _number("queue", wait, shown, wait < run, len(waits), how, hosted)


def waste(facts: Facts, start: datetime, end: datetime) -> Number:
    def of(kind: str) -> tuple[float, float, int]:
        ran = [
            j for j in facts.jobs if j["kind"] == kind and _ran(j) and _in(j["created"], start, end)
        ]
        lost = sum(
            minutes(j["started"], j["completed"])
            for j in ran
            if j["conclusion"] in ("failure", "cancelled")
        )
        return lost, sum(minutes(j["started"], j["completed"]) for j in ran), len(ran)

    lost, total, count = of("local")
    h_lost, h_total, _ = of("hosted")
    how = (
        "execution minutes of jobs that failed or were cancelled over all execution minutes, "
        "on the local runner, job level; a job cancelled while it waited has none to count"
    )
    hosted = f"{h_lost / h_total:.1%}" if h_total else ""
    if not total:
        return _number("waste", None, "", None, 0, how, hosted)
    share = lost / total
    return _number("waste", share, f"{share:.1%}", share < 0.15, count, how, hosted)


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
        if j["kind"] == "local"
        and j["conclusion"] == "failure"
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
        "failed jobs on the local runner, last attempt of a run, that were the pull request's "
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
    return _number(
        "stale", float(len(found)), f"{len(found)} of {len(counted)}", not found, len(counted), how
    )


def green(facts: Facts, start: datetime, end: datetime) -> Number:
    def of(kind: str) -> list[float]:
        found = []
        for one in _merged(facts, start, end):
            ran = [
                j
                for j in facts.jobs
                if j["sha"] == one["head"] and j["event"] == "pull_request" and j["kind"] == kind
            ]
            ok = [j for j in ran if j["conclusion"] == "success"]
            if ok:
                found.append(
                    minutes(min(j["created"] for j in ran), max(j["completed"] for j in ok))
                )
        return found

    local, hosted = of("local"), of("hosted")
    how = (
        "minutes from the first job on a merged pull request's final head to the last green "
        "one, median over the pull requests merged in the period, on the local runner"
    )
    shown_hosted = f"{_text(percentile(hosted, 0.5))} min" if hosted else ""
    if not local:
        return _number("green", None, "", None, 0, how, shown_hosted)
    value = percentile(local, 0.5)
    return _number("green", value, f"{_text(value)} min", value < 15, len(local), how, shown_hosted)


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
    return _number("mainred", value, f"{_text(value)} min", value < 30, seen, how)


def flaky(facts: Facts, start: datetime, end: datetime) -> Number:
    ids: set[str] = set()
    red = [j for j in facts.jobs if j["conclusion"] == "failure" and _in(j["created"], start, end)]
    for job in red:
        if facts.causes[job["job"]] == "flake":
            ids |= set(job["tests"] or [])
    how = (
        "tests that failed on two branches in the period with no runner fault in the log and "
        "no red main to blame; counted by this rule, not by hand"
    )
    if not red:
        return _number("flaky", None, "", None, 0, how)
    return _number("flaky", float(len(ids)), str(len(ids)), len(ids) < 3, len(red), how)


def inode(facts: Facts, start: datetime, end: datetime) -> Number:
    seen = [
        float(j["tmp_inode_pct"])
        for j in facts.jobs
        if j.get("tmp_inode_pct") is not None and _in(j["created"], start, end)
    ]
    how = "the highest /tmp inode use a job wrote with `jbus ci --notice`; nothing writes it yet"
    if not seen:
        return _number("inode", None, "", None, 0, how)
    peak = max(seen)
    return _number("inode", peak, f"{_text(peak)}%", peak < 80, len(seen), how)


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
)


def compute(facts: Facts, start: datetime, end: datetime) -> list[Number]:
    """Count the nine targets over the window from `start` up to `end`."""
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
