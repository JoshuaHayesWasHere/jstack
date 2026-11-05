"""`jbus ci --day`: the day's CI report, `reports/ci-day-<date>.md` in a project's home.

It gives the CI health numbers and main-red for each of the last 7 whole local days, with the n
under each cell, and a before and after for each row of the cicd home that merged. Each number is
a `Measure` of `MEASURES`, and `docs/jbus/measure-the-ci.md`, "The day's report", is its one
definition. In short:

- A day is a local day of the user's zone (the machine's where none is set), midnight to
  midnight, never UTC (`days`). A day with fewer than `FLOOR` pull requests with a `check` run
  reads `no data` for every number from the ledger, its n still shown, since the ledger misses
  runs while jbus is down.
- Every number but main-red comes from the ledger the passes keep (`ci.jsonl`, `ci-prs.jsonl`),
  with jmerge's shadow pull requests (`LINE`) left out. `--day` collects nothing.
- Main-red is the spell method (`spells`): from a failed run of check.yml on a push to main to the
  next success's last update, split at local midnight. It reads main's runs from one
  `gh run list` (`RUNS`), the only call to GitHub. `gh` shows a run's last attempt only, so a red
  that went green on a rerun is no spell. A day older than the oldest run it gave reads `no data`.
- The review step's numbers come from T3 Code's store (`jgauge.spend.reviews`): each thread
  jbus titled `review: <slug>, <round>` is a launch, joined to the pull request its slug's brief
  names on a `Branch:` line (`pulls`), and to when `check` passed at that pull request's newest
  head in the ledger (`Ledger.passed`). They are not under the floor, since the store gives them.
- A day whose shard wait p90 is over `WAVE` seconds is a wave day.
- Before and after (`Shift`): for each row whose brief names the `SCOPE` home and that merged in
  the last `BACK` (transitions.jsonl, its last merge), the median over the `SIDE` busy days before
  its merge day against the `SIDE` after. It is `moved` only when the after-median is outside the
  before-days' least and most, and `held` otherwise. Two rows that merged within `NEAR` of each
  other share their move.

The proposed targets are proposals: no number is held to one, and nothing here raises an alert.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbriefs import home as homes
from jbus import watch
from jbus.ci import ledger, numbers
from jgauge import spend
from jsettings import proc

DAYS, FLOOR, SIDE = 7, 20, 3
WAVE = 300.0
"""The shard wait p90, in seconds, over which a day is a wave day."""
BACK, NEAR, LOOKBACK = timedelta(days=14), timedelta(days=3), timedelta(days=21)
"""The rows merged in the last `BACK` get a before and after; two within `NEAR` share it; the
busy days before a merge are sought at most `LOOKBACK` back."""
REACH = timedelta(days=DAYS) + BACK + LOOKBACK
"""How far back the review launches are read: as far as a day the report gives or a before and
after counts."""
SCOPE = "cicd"
LINE = "jstack/line/"
"""The branches of jmerge's shadow pull requests, which test the line and are no crew's work."""
TRANSITIONS = "transitions.jsonl"
FIRES = time(6, 45)
"""When `jbus-ci-day.timer` fires: a report older than the last of these is stale."""
NO_DATA = "no data"
NEWEST = "## The newest day, "
RUNS = [
    "gh",
    "run",
    "list",
    "-R",
    "{repo}",
    "--workflow",
    "check.yml",
    "--branch",
    "main",
    "--event",
    "push",
    "--limit",
    "400",
    "--json",
    "conclusion,status,createdAt,updatedAt,headSha",
]


def ask(command: list[str]) -> Any:
    """Run `gh`: tests stand in for this."""
    return proc.run(*command, timeout=120)


@dataclass(frozen=True)
class Cell:
    value: float | None
    n: int
    shown: str


@dataclass
class Ledger:
    """What a day's numbers are counted from: the ledger's facts; main's runs as `gh run list`
    gave them, or None with `said`, why there are none; and the review launches T3 Code's store
    gave, or None with `unread`, why there are none, with the pull request each launch's slug
    names (`pulls`)."""

    facts: numbers.Facts
    runs: list[dict[str, Any]] | None
    said: str = ""
    launches: list[spend.Launch] | None = None
    unread: str = ""
    pulls: dict[str, int] = field(default_factory=dict)

    @cached_property
    def passed(self) -> dict[int, datetime | None]:
        """For each pull request whose newest head has a `check` job in the ledger, the first
        completion of a green one at that head, or None where none was green."""
        heads = {int(one["number"]): one.get("head") for one in self.facts.pulls}
        found: dict[int, datetime | None] = {}
        for job in self.facts.jobs:
            pr = job.get("pr")
            if (
                pr is None
                or job["name"] != numbers.CHECK
                or job["event"] != "pull_request"
                or job["sha"] != heads.get(int(pr))
            ):
                continue
            green = job["conclusion"] == "success" and job.get("completed")
            at = jsettings.when(job["completed"]) if green else None
            was = found.get(int(pr))
            found[int(pr)] = was if at is None or (was is not None and was <= at) else at
        return found

    @cached_property
    def spells(self) -> list[tuple[datetime, datetime]]:
        return spells(self.runs or [], self.facts.now)

    @cached_property
    def reach(self) -> datetime | None:
        """The creation of the oldest run `gh` gave: main-red is known from there on."""
        made = [jsettings.when(one["createdAt"]) for one in self.runs or []]
        return min(made) if made else None

    @cached_property
    def shas(self) -> dict[int, set[str]]:
        found: dict[int, set[str]] = defaultdict(set)
        for job in self.facts.jobs:
            if job["event"] == "pull_request" and job.get("pr") is not None:
                found[int(job["pr"])].add(job["sha"])
        return found

    @cached_property
    def walls(self) -> list[tuple[datetime, float]]:
        """Each check run of a pull request whose `check` concluded, as (its first job's
        creation, minutes to its last job's completion)."""
        runs: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for job in self.facts.jobs:
            if job["event"] == "pull_request":
                runs[(job["run"], job["attempt"])].append(job)
        found = []
        for jobs in runs.values():
            if not any(
                j["name"] == numbers.CHECK and j["conclusion"] in ("success", "failure")
                for j in jobs
            ):
                continue
            first = min(jsettings.when(j["created"]) for j in jobs)
            last = max(jsettings.when(j["completed"]) for j in jobs if j.get("completed"))
            found.append((first, (last - first).total_seconds() / 60))
        return found


def spells(runs: list[dict[str, Any]], end: datetime) -> list[tuple[datetime, datetime]]:
    """The spells main was red: each from the creation of a failed run that found main green to
    the last update of the next run to succeed, in the order the runs were created. A run not
    completed, or cancelled or skipped, says nothing. A spell still open runs to `end`."""
    found, red = [], None
    ordered = sorted(runs, key=lambda one: one["createdAt"])
    for one in ordered:
        if one.get("status") != "completed":
            continue
        if one.get("conclusion") == "failure" and red is None:
            red = jsettings.when(one["createdAt"])
        elif one.get("conclusion") == "success" and red is not None:
            found.append((red, jsettings.when(one["updatedAt"])))
            red = None
    if red is not None:
        found.append((red, end))
    return found


def red_minutes(spells: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> float:
    return sum(
        max(0.0, (min(last, end) - max(first, start)).total_seconds() / 60)
        for first, last in spells
    )


def days(
    user: jsettings.Settings, first: date, last: date
) -> list[tuple[date, datetime, datetime]]:
    """Each local day from `first` to `last`, with its start and end in UTC. A day starts at
    local midnight, so a day the clocks change on has 23 or 25 hours."""

    def midnight(one: date) -> datetime:
        return user.local(datetime.combine(one, time())).astimezone(UTC)

    found = []
    one = first
    while one <= last:
        after = one + timedelta(days=1)
        found.append((one, midnight(one), midnight(after)))
        one = after
    return found


def _text(value: float, places: int = 1) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".") if places else f"{value:.0f}"


Count = tuple[float | None, int]
"""A day's value of a number, None where there was nothing to count, and its n."""


def _number(
    count: Callable[[numbers.Facts, datetime, datetime], numbers.Number],
) -> Callable[[Ledger, datetime, datetime], Count]:
    def read(given: Ledger, start: datetime, end: datetime) -> Count:
        one = count(given.facts, start, end)
        return one.value, one.n

    return read


def _shas(given: Ledger, start: datetime, end: datetime) -> Count:
    merged = numbers._merged(given.facts, start, end)
    if not merged:
        return None, 0
    return sum(len(given.shas[int(one["number"])]) for one in merged) / len(merged), len(merged)


def _wall(given: Ledger, start: datetime, end: datetime) -> Count:
    found = [minutes for first, minutes in given.walls if start <= first < end]
    return (numbers.percentile(found, 0.5) if found else None), len(found)


def _launched(given: Ledger, start: datetime, end: datetime) -> list[spend.Launch] | None:
    if given.launches is None:
        return None
    return [one for one in given.launches if start <= one.start < end]


def _by_pull(given: Ledger, start: datetime, end: datetime) -> dict[int, list[spend.Launch]]:
    found: dict[int, list[spend.Launch]] = defaultdict(list)
    for one in _launched(given, start, end) or []:
        if one.slug in given.pulls:
            found[given.pulls[one.slug]].append(one)
    return found


def _launches(given: Ledger, start: datetime, end: datetime) -> Count:
    launched = _launched(given, start, end)
    if launched is None:
        return None, 0
    return len(launched), len(_by_pull(given, start, end))


def _per_pull(
    weigh: Callable[[spend.Launch], float],
) -> Callable[[Ledger, datetime, datetime], Count]:
    def read(given: Ledger, start: datetime, end: datetime) -> Count:
        sums = [
            sum(weigh(one) for one in launched) for launched in _by_pull(given, start, end).values()
        ]
        return (numbers.percentile(sums, 0.5) if sums else None), len(sums)

    return read


def _before_check(given: Ledger, start: datetime, end: datetime) -> Count:
    known = [
        (one, given.passed[pr])
        for pr, launched in _by_pull(given, start, end).items()
        if pr in given.passed
        for one in launched
    ]
    if not known:
        return None, 0
    return sum(1 for one, passed in known if passed is None or one.start < passed), len(known)


def _main_red(given: Ledger, start: datetime, end: datetime) -> Count:
    if given.runs is None or given.reach is None or given.reach > start:
        return None, 0
    ran = [
        one
        for one in given.runs
        if one.get("status") == "completed" and start <= jsettings.when(one["createdAt"]) < end
    ]
    return red_minutes(given.spells, start, end), len(ran)


@dataclass(frozen=True)
class Measure:
    """One number of the day's report: its `name`, what its n counts (`unit`), its proposed
    target (`proposal`, empty where none is proposed), how it reads a day, and how it `write`s a
    value. A `floored` number reads `no data` on a day under `FLOOR` pull requests."""

    key: str
    name: str
    unit: str
    proposal: str
    read: Callable[[Ledger, datetime, datetime], Count]
    write: Callable[[float], str]
    floored: bool = True

    def cell(self, given: Ledger, start: datetime, end: datetime) -> Cell:
        value, n = self.read(given, start, end)
        return Cell(value, n, NO_DATA if value is None else self.write(value))


def _percent(value: float) -> str:
    return f"{value:.0%}"


def _seconds(value: float) -> str:
    return f"{value:.0f} s"


def _minutes(value: float) -> str:
    return f"{_text(value)} min"


def _tokens(value: float) -> str:
    if value >= 1e6:
        return f"{_text(value / 1e6)}M"
    return f"{_text(value / 1e3, 0)}k" if value >= 1e3 else _text(value, 0)


MEASURES = (
    Measure("red_share", "red share", "PRs", "at most 30%", _number(numbers.red_share), _percent),
    Measure("head_shas", "head shas per merged PR", "merged PRs", "at most 3", _shas, _text),
    Measure(
        "wait_p90_shard",
        "shard wait p90",
        "jobs",
        "at most 60 s",
        _number(numbers.wait_p90_shard),
        _seconds,
    ),
    Measure(
        "wait_p90_macos",
        "macos wait p90",
        "jobs",
        "at most 120 s",
        _number(numbers.wait_p90_macos),
        _seconds,
    ),
    Measure("wall", "PR check wall p50", "runs", "at most 10 min", _wall, _minutes),
    Measure(
        "open_to_merge",
        "open to merge p50",
        "merged PRs",
        "at most 1 h",
        _number(numbers.open_to_merge),
        lambda v: f"{_text(v)} h",
    ),
    Measure(
        "first_check_own_red",
        "first-check own red",
        "PRs",
        "",
        _number(numbers.first_check_own_red),
        _percent,
    ),
    Measure("main_red", "main-red", "runs", "at most 30 min", _main_red, _minutes, floored=False),
    Measure(
        "review_launches",
        "review launches",
        "PRs",
        "",
        _launches,
        lambda v: _text(v, 0),
        floored=False,
    ),
    Measure(
        "review_input",
        "review input tokens per PR p50",
        "PRs",
        "",
        _per_pull(lambda one: one.tokens.input),
        _tokens,
        floored=False,
    ),
    Measure(
        "review_output",
        "review output tokens per PR p50",
        "PRs",
        "",
        _per_pull(lambda one: one.tokens.output),
        _tokens,
        floored=False,
    ),
    Measure(
        "review_wall",
        "review active wall per PR p50",
        "PRs",
        "",
        _per_pull(lambda one: one.active / 60),
        _minutes,
        floored=False,
    ),
    Measure(
        "review_before_check",
        "review launches before check",
        "launches",
        "",
        _before_check,
        lambda v: _text(v, 0),
        floored=False,
    ),
)


@dataclass(frozen=True)
class Day:
    date: date
    cells: dict[str, Cell]

    @property
    def prs(self) -> int:
        return self.cells["red_share"].n

    @property
    def busy(self) -> bool:
        return self.prs >= FLOOR

    @property
    def wave(self) -> bool:
        shard = self.cells["wait_p90_shard"].value
        return shard is not None and shard > WAVE

    @property
    def label(self) -> str:
        return f"{self.date:%m-%d}" + (" wave" if self.wave else "")


@dataclass
class Days:
    """The days of a ledger, each counted once, when first asked for."""

    given: Ledger
    user: jsettings.Settings
    kept: dict[date, Day] = field(default_factory=dict)

    def __getitem__(self, when: date) -> Day:
        if when not in self.kept:
            ((_, start, end),) = days(self.user, when, when)
            cells = {one.key: one.cell(self.given, start, end) for one in MEASURES}
            if cells["red_share"].n < FLOOR:
                cells = {
                    one.key: cells[one.key]
                    if not one.floored
                    else Cell(None, cells[one.key].n, NO_DATA)
                    for one in MEASURES
                }
            self.kept[when] = Day(when, cells)
        return self.kept[when]


def verdict(before: list[float], after: list[float]) -> str:
    """`moved` where the median of the days after is outside the least and most of the days
    before, `held` where it is inside, and `no data` without `SIDE` days on each side."""
    if len(before) < SIDE or len(after) < SIDE:
        return NO_DATA
    middle = statistics.median(after)
    return "moved" if middle < min(before) or middle > max(before) else "held"


@dataclass(frozen=True)
class Shift:
    """A row that merged, with the busy days before and after its merge day, and the rows that
    merged within `NEAR` of it."""

    slug: str
    merged: date
    before: list[Day]
    after: list[Day]
    shared: list[str]


def merges(config: jbus.Config, project: jbus.Project, now: datetime) -> list[tuple[str, datetime]]:
    """Each row of the `SCOPE` home that merged in the last `BACK`, at its last merge, oldest
    first. The row's home is the one its brief names."""
    state, home = config.state(project), config.home(project)
    last: dict[str, datetime] = {}
    for one in ledger.read(state / TRANSITIONS):
        if one.get("to") == "merged" and one.get("slug") and one.get("at"):
            last[one["slug"]] = jsettings.when(one["at"])
    found = []
    for slug, at in last.items():
        if not now - BACK <= at <= now:
            continue
        try:
            brief = (state / "briefs" / f"{slug}.md").read_text()
        except OSError:
            continue
        if homes.home_of(home, brief) == home / SCOPE:
            found.append((slug, at))
    return sorted(found, key=lambda one: one[1])


def shifts(
    merged: list[tuple[str, datetime]], by_day: Days, user: jsettings.Settings, newest: date
) -> list[Shift]:
    found = []
    for slug, at in merged:
        on = user.local(at).date()
        before, one = [], on - timedelta(days=1)
        while len(before) < SIDE and one >= on - LOOKBACK:
            if by_day[one].busy:
                before.insert(0, by_day[one])
            one -= timedelta(days=1)
        after, one = [], on + timedelta(days=1)
        while len(after) < SIDE and one <= newest:
            if by_day[one].busy:
                after.append(by_day[one])
            one += timedelta(days=1)
        near = [other for other, when in merged if other != slug and abs(when - at) <= NEAR]
        found.append(Shift(slug, on, before, after, near))
    return found


def _side(chosen: list[Day]) -> str:
    named = ", ".join(one.label for one in chosen) or "none"
    return named if len(chosen) == SIDE else f"{named} ({len(chosen)} of {SIDE})"


def _moved(shift: Shift, measure: Measure) -> str:
    before = [one.cells[measure.key] for one in shift.before]
    after = [one.cells[measure.key] for one in shift.after]
    said = verdict(
        [c.value for c in before if c.value is not None],
        [c.value for c in after if c.value is not None],
    )
    if said == NO_DATA:
        return NO_DATA
    middle = [
        statistics.median(c.value for c in cells if c.value is not None)
        for cells in (before, after)
    ]
    return f"{measure.write(middle[0])} to {measure.write(middle[1])}, {said}"


def body(
    by_day: Days,
    shown: list[Day],
    moves: list[Shift],
    given: Ledger,
    user: jsettings.Settings,
    now: datetime,
) -> str:
    def row(*cells: str) -> str:
        return "| " + " | ".join(cells) + " |"

    table = [
        row("number", "proposed", *(one.label for one in shown)),
        row("---", "---", *("---" for _ in shown)),
    ]
    for one in MEASURES:
        table.append(
            row(one.name, one.proposal or "none", *(d.cells[one.key].shown for d in shown))
        )
        table.append(row("", "", *(f"{d.cells[one.key].n} {one.unit}" for d in shown)))
    if given.runs is None:
        reach = f"gh run list did not answer: {given.said}. Main-red reads `no data`."
    elif given.reach is None:
        reach = "gh run list gave no run of main, so main-red reads `no data`."
    else:
        reach = (
            f"Main-red reads the {len(given.runs)} runs of check.yml on a push to main that "
            f"`gh run list` gave, back to {user.stamp(given.reach)}; a day that starts before "
            "that reads `no data`. gh shows a run's last attempt only, so a red that went "
            "green on a rerun is no spell."
        )
    if given.launches is None:
        store = f"T3 Code's store was not read: {given.unread}. The review numbers read `no data`."
    else:
        store = (
            f"The review numbers read the {len(given.launches)} review launches T3 Code's store"
            f" gave for the {len(given.pulls)} slugs whose brief names a pull request on a"
            " `Branch:` line; a launch of a slug that names none is in `review launches` alone,"
            " and a launch counts in `before check` only where the ledger has a `check` job at"
            " its pull request's newest head."
        )
    names = [one.name for one in MEASURES]
    moved = [
        row("row", "merged", "before", "after", *names, "notes"),
        row(*("---" for _ in range(len(names) + 5))),
    ]
    for shift in moves:
        notes = [f"shared with {', '.join(shift.shared)}"] if shift.shared else []
        if any(one.wave for one in shift.before + shift.after):
            notes.append("wave")
        moved.append(
            row(
                shift.slug,
                f"{shift.merged:%m-%d}",
                _side(shift.before),
                _side(shift.after),
                *(_moved(shift, one) for one in MEASURES),
                "; ".join(notes),
            )
        )
    newest = shown[-1]
    lines = [
        f"- {one.name}: {newest.cells[one.key].shown} (n {newest.cells[one.key].n} {one.unit})"
        for one in MEASURES
    ]
    return "\n".join(
        [
            f"# CI by day, {shown[0].date} to {newest.date}",
            "",
            f"Written {user.stamp(now)} by `jbus ci --day`. Each day is a local day of"
            f" {user.word(now)}, midnight to midnight, never UTC. Each number is defined in"
            ' features/jbus/docs/jbus/measure-the-ci.md, "The day\'s report", and the row under'
            f" it is its n. A day with fewer than {FLOOR} pull requests with a `check` run reads"
            " `no data` for every number from the ledger. A day marked `wave` had a shard wait"
            f" p90 over {WAVE:.0f} s. The targets are proposals: none is held, and nothing pages.",
            "",
            reach,
            "",
            store,
            "",
            "## By day",
            "",
            *table,
            "",
            "## Before and after each cicd row that merged",
            "",
            f"Each row of the {SCOPE} home that merged in the last {BACK.days} days: the median"
            f" over the {SIDE} busy days (at least {FLOOR} pull requests) before its merge day"
            f" against the {SIDE} after. `moved` means the median after is outside the least and"
            f" most of the days before. `shared with` names a row that merged within"
            f" {NEAR.days} days, and `wave` a wave day among the days counted.",
            "",
            *(moved if moves else ["No row of the home merged in that time."]),
            "",
            f"{NEWEST}{newest.date}",
            "",
            *lines,
            "",
        ]
    )


def facts_of(state: Path, now: datetime) -> numbers.Facts:
    """The ledger's facts, without jmerge's shadow pull requests."""

    def ours(one: dict[str, Any]) -> bool:
        return not str(one.get("branch") or "").startswith(LINE)

    return numbers.Facts(
        [one for one in ledger.read(state / ledger.JOBS) if ours(one)],
        [one for one in ledger.read(state / ledger.PULLS) if ours(one)],
        ledger.read(state / "events.jsonl"),
        now,
    )


def reviewed(
    config: jbus.Config, project: jbus.Project, now: datetime
) -> tuple[list[spend.Launch] | None, str, dict[str, int]]:
    """The review launches of the project's T3 Code project back to `REACH` before `now`, or None
    and why, and the pull request each launch's slug names: the first `Branch:` line of its brief
    that names one, as `jbus.watch.tied` reads it."""
    try:
        launches = spend.reviews(spend.STORE, project.project_id, now - REACH, now)
    except spend.Refused as error:
        return None, str(error), {}
    tasks, pulls = config.home(project) / "tasks", {}
    for slug in {one.slug for one in launches}:
        try:
            lines = (tasks / f"{slug}.md").read_text(errors="replace").splitlines()
        except OSError:
            continue
        named = [watch.named(line)[1] for line in lines if line.startswith("Branch:")]
        if number := next((one for one in named if one), ""):
            pulls[slug] = int(number)
    return launches, "", pulls


def main_runs(repo: str) -> tuple[list[dict[str, Any]] | None, str]:
    """Main's runs of check.yml from the one `gh run list`, or None and why."""
    done = ask([part.format(repo=repo) for part in RUNS])
    if done.returncode:
        return None, " ".join(str(done.stderr).split())[:200] or f"gh exit {done.returncode}"
    try:
        runs = json.loads(done.stdout)
    except ValueError:
        return None, "gh gave no JSON"
    if not isinstance(runs, list) or not all(isinstance(one, dict) for one in runs):
        return None, "gh gave no list of runs"
    return runs, ""


def one(config: jbus.Config, project: jbus.Project, now: datetime, repo: str | None) -> int:
    """Write the day's report of one project, and nothing else."""
    user = config.user
    runs, said = main_runs(repo) if repo else (None, "the checkout has no GitHub origin")
    launches, unread, pulls = reviewed(config, project, now)
    given = Ledger(facts_of(config.state(project), now), runs, said, launches, unread, pulls)
    by_day = Days(given, user)
    newest = user.local(now).date() - timedelta(days=1)
    shown = [by_day[when] for when, _, _ in days(user, newest - timedelta(days=DAYS - 1), newest)]
    moves = shifts(merges(config, project, now), by_day, user, newest)
    path = config.home(project) / "reports" / f"ci-day-{user.day(now)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body(by_day, shown, moves, given, user, now))
    print(f"ci: day report {path}")
    return 0


_NAME = re.compile(r"ci-day-(\d{4}-\d{2}-\d{2})\.md")


def latest(home: Path, now: datetime, user: jsettings.Settings) -> dict[str, Any] | None:
    """The newest day's report of a home, for the digest: its `path`, its `date`, the `day` it
    gives last, that day's `lines`, and whether it is `stale`, written before the timer's last
    run. None where there is no report it can read."""
    try:
        named = sorted(
            (found[1], path)
            for path in (home / "reports").glob("ci-day-*.md")
            if (found := _NAME.fullmatch(path.name))
        )
        written, path = named[-1]
        text = path.read_text()
    except (OSError, IndexError):
        return None
    part = text.split(NEWEST, 1)
    if len(part) < 2:
        return None
    day, _, rest = part[1].partition("\n")
    lines = [line[2:] for line in rest.split("\n## ", 1)[0].splitlines() if line.startswith("- ")]
    local = user.local(now)
    fired = local.date() - timedelta(days=0 if local.time() >= FIRES else 1)
    return {
        "path": str(path),
        "date": written,
        "day": day.strip(),
        "stale": date.fromisoformat(written) < fired,
        "lines": lines,
    }
