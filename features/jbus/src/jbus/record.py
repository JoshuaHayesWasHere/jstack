"""jbus records the last pass in `pass.json`, in the machine-wide state directory.

The pass writes the record twice, under the pass's lock. `Record.start` writes the start with no
end, so a pass that hangs or dies shows as started and not ended. `Record.end` writes the end and
the seconds the pass took. For each project it also writes what the pass saw of the project's open
rows: how many unsettled threads each row has, the thread's status and last update as T3 Code gave
them, and the pull request's checks as GitHub gave them. A row stays open until its pull request
merges. Beside the rows, the record lists the project's `threads`: every thread that is not settled,
a crew's or not, with its role and its liveness (`live`).

When the pass cannot write the record, it says `pass record failed` in the journal and goes on. If
the write that failed was the end, the file keeps the start with no end, as it does for a pass that
died: the journal and the status file's `last_pass` show which of the two happened.

The pass reads the seconds from a clock that keeps counting while the machine is suspended, and the
end is the start plus those seconds.

A project's rows carry `seen`, the start of the pass that saw them. For a project that a pass could
not ask T3 Code or GitHub about, the record keeps what the pass before saw, under that pass's
`seen`. It does the same while a pass has not ended yet. The status file's `last_pass` moves only
when a pass ends; this file's `started` moves when one begins.

`silent` names, for each project the pass could not ask about, the source that did not answer:
`T3 Code` or `GitHub`. Such a pass derived no row of that project, so the project's queue stays as
an earlier pass left it. When a pass starts, the record keeps the `silent` entries of the pass
before, until the end of the new pass writes which sources answered. If a pass saw nothing of a
project and names no source for it, as when the pass raised, the record keeps the project's entry.
Only a pass that saw the project's rows removes the entry.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from jbriefs.home import thread_of
from jbus import Config, alert, passes, project, read_json, signin, t3, wake, write_json
from jbus.queue import Row
from jbus.watch import NEVER, World, checks

if TYPE_CHECKING:
    from jbus.cli import Half

Say = Callable[[str], None]


def clock() -> float:
    boot = getattr(time, "CLOCK_BOOTTIME", None)
    return time.monotonic() if boot is None else time.clock_gettime(boot)


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read(config: Config) -> dict[str, Any]:
    kept = read_json(config.pass_path, {})
    return kept if isinstance(kept, dict) else {}


def _kept(config: Config, key: str = "projects") -> dict[str, Any]:
    """Return what earlier passes left under `key` for each project that the config still
    names: what they saw, or, under `silent`, the source that they could not ask."""
    projects = read(config).get(key)
    names = {project.name for project in config.projects}
    if not isinstance(projects, dict):
        return {}
    return {name: seen for name, seen in projects.items() if name in names}


@dataclass
class Record:
    """A `Record` is the record of one pass: the time the pass began, by both clocks, and what
    the passes before it saw."""

    config: Config
    now: datetime
    began: float = field(default_factory=lambda: clock())
    kept: dict[str, Any] = field(init=False)
    silent: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.kept = _kept(self.config)
        self.silent = _kept(self.config, "silent")

    def _write(
        self, seconds: float | None, projects: dict[str, Any], silent: dict[str, Any]
    ) -> None:
        ended = None if seconds is None else stamp(self.now + timedelta(seconds=seconds))
        said = {
            "started": stamp(self.now),
            "ended": ended,
            "seconds": seconds,
            "projects": projects,
            "silent": silent,
        }
        write_json(self.config.pass_path, said, mode=0o600)

    def start(self) -> None:
        self._write(None, self.kept, self.silent)

    def end(self, saw: dict[str, dict[str, Any]], silent: dict[str, str]) -> None:
        """Write the end of the pass. It holds what the pass saw of each project, its `rows` and
        its `threads`, and, for each project the pass could not ask about, the source that did
        not answer."""
        seen = {name: {"seen": stamp(self.now), **found} for name, found in saw.items()}
        before = {name: source for name, source in self.silent.items() if name not in saw}
        self._write(round(clock() - self.began, 1), self.kept | seen, before | silent)


def _time(given: Any) -> str | None:
    """Return a time as GitHub gave it, or None for a time that is not set, which `gh` prints
    as the year 1."""
    return given if isinstance(given, str) and given and not given.startswith("0001-") else None


def _order(check: dict[str, Any]) -> tuple[bool, str]:
    """Return the sort key of a check, which puts a check that waits to start after every
    check that started."""
    started = _time(check.get("startedAt"))
    return (check.get("status", "COMPLETED") != "COMPLETED" and started is None, started or "")


def _latest(pull: dict[str, Any]) -> dict[str, Any] | None:
    """Return the check of a pull request that started last, or, among checks that tie, the
    one listed last."""
    rollup = [check for check in pull.get("statusCheckRollup") or [] if isinstance(check, dict)]
    if not rollup:
        return None
    check = max(reversed(rollup), key=_order)
    return {
        "name": check.get("name") or check.get("context") or "",
        "state": checks({"statusCheckRollup": [check], NEVER: pull.get(NEVER)}),
        "started": _time(check.get("startedAt")),
        "completed": _time(check.get("completedAt")),
    }


THREAD = (
    "id",
    "title",
    "role",
    "slug",
    "status",
    "createdAt",
    "updatedAt",
    "items",
    "wrote",
    "live",
    "silent",
    "run",
    "run_started",
    "queued",
    "pending",
    "page",
)


def seen(config: Config, name: str) -> list[dict[str, Any]]:
    """Return the threads of a project as the last record lists them, or none where the record
    has no list."""
    kept = _kept(config).get(name)
    listed = kept.get("threads") if isinstance(kept, dict) else None
    return [one for one in listed if isinstance(one, dict)] if isinstance(listed, list) else []


def threads(out: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Return every thread that is out as this pass saw it (`threads.out`), cut to the keys in
    `THREAD`, or None where T3 Code could not list them."""
    return None if out is None else [{key: one[key] for key in THREAD} for one in out]


def rows(
    world: World,
    table: list[Row],
    out: list[dict[str, Any]] | None = None,
    gone: frozenset[str] = frozenset(),
) -> dict[str, dict[str, Any]]:
    """Return each open row of the queue as T3 Code and GitHub described it to this pass.

    `live` is the liveness of the row's one thread, where `out` has it. `gone` marks a row that
    wrote nothing and whose launched thread is no longer on T3 Code's list (`watch.gone`).
    """
    live = {one["id"]: one["live"] for one in out or []}
    seen = {}
    for row in table:
        slug = row["slug"]
        if slug in world.merged and slug not in world.open:
            continue
        thread, pull = world.thread(slug) or {}, world.open.get(slug)
        seen[slug] = {
            "threads": len(world.threads.get(slug, [])),
            "thread_status": thread.get("status"),
            "thread_updated": thread.get("updatedAt"),
            "live": live.get(thread.get("threadId")),
            "gone": slug in gone,
            "checks": checks(pull) if pull else "",
            "check": _latest(pull) if pull else None,
        }
    return seen


def _hook(config: Config, box: wake.Box, route: wake.Route, key: str) -> dict[str, Any]:
    """Return what the status file says of one webhook of a project: its streak, its last
    error and what waits in its outbox."""
    failing = alert.streak(config.state_dir, key)
    return {
        "failed_wakes": failing.count if failing else 0,
        "last_error": box.marks(route).get("last_error", ""),
        "outbox": box.waiting(route),
    }


def stranded(config: Config) -> dict[str, dict[str, int]]:
    """Return, for each project that has one, each outbox of a route its `wake` leaves out that
    still holds events, with how many. The next pass moves them (`wake.Box.rehome`), and
    `jbus status` counts them again as they stand."""
    found = {}
    for one in config.projects:
        box = wake.Box(config.state(one), one, config.webhook, config.blocking)
        held = {route.name: box.waiting(route) for route in box.left}
        if any(held.values()):
            found[one.name] = {name: count for name, count in held.items() if count}
    return found


def alerts(config: Config, now: datetime) -> list[str]:
    """Return the alert line of each webhook of each project whose streak alerted, with the error
    the webhook gave last (`alert.failing`)."""
    return [
        line
        for one in config.projects
        for _, line in alert.failing(passes.Pass(config, one, now, lambda _: None))
    ]


def status(config: Config, now: datetime) -> dict[str, Any]:
    """Return what the status file holds. Most of it comes back from the files the pass left.
    The rest is the homes not on the bus, which no pass writes (`project.missing`), and each
    scratch home, with the thread in its `home-id` and none of a repo's fields."""
    expires = t3.expiry(config.token_path)
    projects = {}
    for one in config.projects:
        box = wake.Box(config.state(one), one, config.webhook, config.blocking)
        marks = box.marks()
        first, *rest = box.routes
        projects[one.name] = {
            **_hook(config, box, first, alert.key_of(one.name, first)),
            "wake": one.wake,
            "sign_in": signin.expiring(config, now),
            "sweep": marks.get("sweep", ""),
        }
        for route in rest:
            part = "top_level" if route.top else "webhook"
            projects[one.name][part] = _hook(config, box, route, alert.key_of(one.name, route))
        if box.blocking is not None:
            key = alert.blocking(one.name)
            projects[one.name]["blocking"] = _hook(config, box, box.blocking, key)
    return {
        "alerts": alerts(config, now),
        "stranded": stranded(config),
        "last_pass": config.user.stamp(now),
        "token_expires": config.user.stamp(expires) if expires else None,
        "sign_in_reminder": signin.plan(config, now),
        "projects": projects,
        "streaks": alert.streaks(config.state_dir),
        "homes_off_bus": project.missing(config),
        "scratch": {
            one.name: {
                "project_id": one.project_id,
                "home_thread": thread_of(config.home(one.addressee())),
            }
            for one in config.scratch
        },
    }


def write_status(
    config: Config, now: datetime, last: dict[str, Any], raised: dict[str, str], say: Say
) -> None:
    """Write the status file at the end of a pass, with the error of each project that
    raised as its `last_error`. It names the homes that have no project in the config in one
    line, on the pass where that list changes (`project.missing`)."""
    report = status(config, now)
    if report["homes_off_bus"] != last.get("homes_off_bus", []):
        say(f"homes not on the bus: {', '.join(report['homes_off_bus']) or 'none'}")
    for name, why in raised.items():
        if name in report["projects"]:
            report["projects"][name]["last_error"] = why
    write_json(config.status_path, report, mode=0o600)


def saw(halves: list[Half]) -> dict[str, dict[str, Any]]:
    """Return the open rows and the threads out of each project whose pass had answers from
    T3 Code and GitHub."""
    found = {}
    for half in halves:
        run, world, table = half.run, half.seen.world, half.rows
        if world is None or table is None:
            continue
        found[run.project.name] = {
            "rows": rows(world, table, half.out, half.gone),
            "threads": threads(half.out),
        }
    return found


def silent(halves: list[Half]) -> dict[str, str]:
    """Return the source that did not answer, for each project whose pass could not ask: T3
    Code, or GitHub where T3 Code answered. A blind pass asked both sources and is not silent."""
    return {
        half.run.project.name: "T3 Code" if half.seen.out is None else "GitHub"
        for half in halves
        if half.seen.world is None and not (half.blind and half.seen.out is not None)
    }


def heartbeat(run: passes.Pass, last: dict[str, Any]) -> None:
    """Say what the status file said, once per project, on the first pass of each hour.

    The line is quiet: it goes to the log, and jbus never posts it. The hour is UTC's, so the
    heartbeat does not skip the hour that a clock change repeats. Each webhook of the project whose
    streak alerted gets a heartbeat line of its own, its alert line (`alert.failing`).
    """
    mine = last.get("projects", {}).get(run.project.name, {})
    line = (
        f"heartbeat: jbus alive, last pass {last.get('last_pass', '')[11:] or 'none'}, "
        f"failed wakes {mine.get('failed_wakes', 0)}, last error {mine.get('last_error') or 'none'}"
    )
    hour = f"{run.now.astimezone(UTC):%Y-%m-%d %H}"
    run.find("", "heartbeat", line, key=hour)
    for key, failing in alert.failing(run):
        run.find("", "heartbeat", failing, key=f"{hour} {key}")
