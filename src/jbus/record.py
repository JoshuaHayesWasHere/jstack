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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from jbus import Config, read_json, write_json
from jbus.queue import Row
from jbus.watch import World, checks


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
        "state": checks({"statusCheckRollup": [check]}),
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
