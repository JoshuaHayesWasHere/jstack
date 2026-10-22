"""The record of the last pass: `pass.json` in the machine-wide state directory.

It is written twice a pass, under the pass's lock. `Record.start` writes the start with no
end, so a pass that hangs or dies shows as started and not ended. `Record.end` writes the
end, the seconds the pass took, and for each project what the pass saw of its open rows:
how many threads the row has that are not settled, the thread's status and last update as
T3 Code gave them, and the pull request's checks as GitHub gave them. A row is open until
its pull request is merged. Beside the rows are the project's `threads`: every thread that
is not settled, a crew's or not, with its role and its liveness (`live`).

A record that cannot be written is said in the journal as `pass record failed`, and the
pass goes on. When that is the end, the file keeps the start with no end, as it does for a
pass that died: the journal and the status file's `last_pass` tell the two apart.

The seconds are read from a clock that keeps counting while the machine is suspended, and
the end is the start plus those seconds.

A project's rows carry `seen`, the start of the pass that saw them. A pass that could not
ask T3 Code or GitHub about a project, and one that has not ended yet, keep what the pass
before saw, under that pass's `seen`. The status file's `last_pass` moves only when a pass
ends; this file's `started` moves when one begins.

`silent` names, for each project the pass could not ask about, the source that did not
answer: `T3 Code` or `GitHub`. Such a pass derived no row of that project, so its queue
stands as an earlier pass left it. A pass that starts keeps what the one before it said,
until its own end says what answered it. A pass that saw nothing of a project and names no
source for it, as one that raised, keeps the entry the project had: only a pass that saw
the project's rows takes it out.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from jbriefs.home import thread_of
from jbus import Config, alert, project, read_json, signin, t3, wake, write_json
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
    """What earlier passes saw, or under `silent` could not ask, of the projects the config
    still names."""
    projects = read(config).get(key)
    names = {project.name for project in config.projects}
    if not isinstance(projects, dict):
        return {}
    return {name: seen for name, seen in projects.items() if name in names}


@dataclass
class Record:
    """One pass's record: when it began, by both clocks, and what the passes before saw."""

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
        """Write the end of the pass, with what it saw of each project, its `rows` and its
        `threads`, and the source that did not answer for each project it could not ask about."""
        seen = {name: {"seen": stamp(self.now), **found} for name, found in saw.items()}
        before = {name: source for name, source in self.silent.items() if name not in saw}
        self._write(round(clock() - self.began, 1), self.kept | seen, before | silent)


def _time(given: Any) -> str | None:
    """A time as GitHub gave it. `gh` prints one that is not set as the year 1: that is none."""
    return given if isinstance(given, str) and given and not given.startswith("0001-") else None


def _order(check: dict[str, Any]) -> tuple[bool, str]:
    """A check that waits to start is later than every check that started."""
    started = _time(check.get("startedAt"))
    return (check.get("status", "COMPLETED") != "COMPLETED" and started is None, started or "")


def _latest(pull: dict[str, Any]) -> dict[str, Any] | None:
    """The check of a pull request that started last, or the last listed among equals."""
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
    """The threads of a project as the last record has them: none where it has no list."""
    kept = _kept(config).get(name)
    listed = kept.get("threads") if isinstance(kept, dict) else None
    return [one for one in listed if isinstance(one, dict)] if isinstance(listed, list) else []


def threads(out: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Every thread that is out as this pass saw it (`threads.out`), cut to `THREAD`. None
    where T3 Code could not list them."""
    return None if out is None else [{key: one[key] for key in THREAD} for one in out]


def rows(
    world: World,
    table: list[Row],
    out: list[dict[str, Any]] | None = None,
    gone: frozenset[str] = frozenset(),
) -> dict[str, dict[str, Any]]:
    """Each open row of the queue as this pass's answers from T3 Code and GitHub have it.

    `live` is the liveness of the row's one thread, where `out` has it, and `gone` says a
    row whose launched thread T3 Code no longer lists and that wrote nothing (`watch.gone`).
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
    """What the status file says of one webhook of a project: its streak, its last error and
    what waits in its outbox."""
    failing = alert.streak(config.state_dir, key)
    return {
        "failed_wakes": failing.count if failing else 0,
        "last_error": box.marks(route).get("last_error", ""),
        "outbox": box.waiting(route),
    }


def status(config: Config, now: datetime) -> dict[str, Any]:
    """What the status file holds: read back from what the pass left, the homes not on the
    bus, which no pass leaves (`project.missing`), and each scratch home with the thread in its
    `home-id` and no field of a repo's."""
    expires = t3.expiry(config.token_path)
    projects = {}
    for one in config.projects:
        box = wake.Box(config.state(one), one, config.webhook, config.blocking)
        marks = box.marks()
        projects[one.name] = {
            **_hook(config, box, box.routes[0], alert.webhook(one.name)),
            "sign_in": signin.expiring(config, now),
            "sweep": marks.get("sweep", ""),
        }
        for route in box.routes[1:]:
            key = alert.top_level(one.name)
            projects[one.name]["top_level"] = _hook(config, box, route, key)
        if box.blocking is not None:
            key = alert.blocking(one.name)
            projects[one.name]["blocking"] = _hook(config, box, box.blocking, key)
    return {
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
    raised as its `last_error`. The homes that have no project in the config are said in
    one line, on the pass their list changes (`project.missing`)."""
    report = status(config, now)
    if report["homes_off_bus"] != last.get("homes_off_bus", []):
        say(f"homes not on the bus: {', '.join(report['homes_off_bus']) or 'none'}")
    for name, why in raised.items():
        if name in report["projects"]:
            report["projects"][name]["last_error"] = why
    write_json(config.status_path, report, mode=0o600)


def saw(halves: list[Half]) -> dict[str, dict[str, Any]]:
    """The open rows and the threads out of each project whose pass had answers from T3
    Code and GitHub."""
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
    """The source that did not answer, for each project whose pass could not ask: T3 Code,
    or GitHub where T3 Code answered. A pass that is blind asked both and is not one."""
    return {
        half.run.project.name: "T3 Code" if half.seen.out is None else "GitHub"
        for half in halves
        if half.seen.world is None and not (half.blind and half.seen.out is not None)
    }


def heartbeat(run: wake.Pass, last: dict[str, Any]) -> None:
    """The first pass of each hour says what the status file said, once per project.

    It is quiet: it is in the log, and is never posted.
    The hour is UTC's, so the hour a clock change repeats is not skipped.
    """
    mine = last.get("projects", {}).get(run.project.name, {})
    line = (
        f"heartbeat: jbus alive, last pass {last.get('last_pass', '')[11:] or 'none'}, "
        f"failed wakes {mine.get('failed_wakes', 0)}, last error {mine.get('last_error') or 'none'}"
    )
    run.find("", "heartbeat", line, key=f"{run.now.astimezone(UTC):%Y-%m-%d %H}")
