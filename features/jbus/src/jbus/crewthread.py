"""Which thread is a row's crew: one answer, `crew`, which every reader of a crew's thread calls.

A crew's thread is carried in three places jbus keeps: the launch records under `launches/`, one
for each launch jbus made (`jbus.launches`); the `Thread:` line of the row's brief under `tasks/`,
or of its request under `scouts/`; and the `thread` column of the queue's row. T3 Code's title is a
fourth, which only the pass reads (`watch.World.thread`).

The brief's line is the answer. jbus writes it at each launch it makes, a resume too, and a home
that resumes a crew by hand on a new thread writes it there (the home skill's pickup), with no
launch record of jbus's. So a line that names a thread no launch record names is a hand resume, and
it stands. One case is not: a line that names an older launch's thread while a newer launch names
another is a pass that died between the newer launch's record and its line, and the newest launch is
the crew. A brief with no line has the newest launch's thread. The queue's column is derived from
the answer on each pass (`jbus.states.derive`), and read back only for a row the other two say
nothing of.

| The brief's line | The launch records | The crew |
|---|---|---|
| none | none | none |
| none | the newest names T | T |
| names T | name no T, or T is the newest | T |
| names T | an older one names T, the newest U | U, and the next pass moves the line |
| none | none, and the queue's column names T | T, a crew its home launched with no line |

Each write of a crew's new thread is `move`: the brief's line and the queue's column under the
queue's lock, in one step. `repair`, at the start of each pass, moves a line the table's last row
says lags. `disagreements` names each row whose carriers do not name one thread, which
`jbus crew-threads` prints.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jbus
import jsettings
from jbriefs import parse
from jbus import queue, verbs
from jbus.launches import records

if TYPE_CHECKING:
    from jbus.passes import Pass

KINDS = {queue.CREW: "tasks", queue.SCOUT: "scouts"}


def newest(found: list[tuple[Path, dict[str, Any]]]) -> list[tuple[Path, dict[str, Any]]]:
    """Return the launch records in the order they were made: a resume's name sorts anywhere."""
    return sorted(found, key=lambda one: str(one[1].get("at") or ""))


def _launches(run: Pass, slug: str, role: str = "") -> list[str]:
    """The threads of the slug's launches, oldest first, each as T3 Code names it."""
    found = newest(records(run, slug, role))
    return [jsettings.thread_id(str(r["thread"])) for _, r in found if r.get("thread")]


def _line(run: Pass, slug: str) -> tuple[str, bool]:
    """The thread on the `Thread:` line of the slug's brief under `tasks/`, else of its request
    under `scouts/`, as `jbriefs.home.thread_of` reads it, and whether either file is there."""
    there = False
    for kind in KINDS.values():
        try:
            text = (run.home / kind / f"{slug}.md").read_text(errors="replace")
        except OSError:
            continue
        there = True
        if found := parse.thread_of(text):
            return jsettings.thread_id(found), there
    return "", there


def _answer(line: str, launches: list[str]) -> str:
    if not launches:
        return line
    last = launches[-1]
    if not line or (line != last and line in launches[:-1]):
        return last
    return line


def crew(run: Pass, slug: str, role: str = "", *, kept: bool = True) -> str:
    """Return the thread of the slug's crew, or nothing where it has none: see the module. `role`
    keeps the launch records of that role only, as `jbus.launches.records` does. A row whose home
    launched its crew and wrote no line has the thread its queue row names, the one the last pass
    listed; the pass that derives that column gives no `kept`, so it is never its own answer."""
    line, _ = _line(run, slug)
    if found := _answer(line, _launches(run, slug, role)):
        return found
    row = (queue.fresh(run.state, slug) or {}) if kept else {}
    return jsettings.thread_id(str(row.get("thread") or ""))


def tended(run: Pass, slug: str) -> bool:
    """Say whether the slug's crew is one jbus tends: jbus launched it, or its queue row names the
    thread its home launched. A brief alone with a `Thread:` line is no row of jbus's, and is not
    told of its pull request."""
    return bool(_launches(run, slug) or (queue.fresh(run.state, slug) or {}).get("thread"))


def write_line(run: Pass, slug: str, thread: str, kind: str = "tasks") -> None:
    """Put `Thread: <id>` in the head of `<kind>/<slug>.md`, in place of the line it had, or above
    the first `## ` where it had none, so it is above any Result a fast crewmate has written."""
    path, line = run.home / kind / f"{slug}.md", f"Thread: {thread}"
    try:
        lines = path.read_text().splitlines()
    except (OSError, ValueError):
        return
    if line in lines:
        return
    was = next((at for at, one in enumerate(lines) if one.startswith("Thread:")), None)
    if was is not None:
        lines[was] = line
    else:
        head = next((at for at, one in enumerate(lines) if one.startswith("## ")), len(lines))
        lines.insert(head, line)
    temporary = path.with_name(path.name + ".thread")
    temporary.write_text("\n".join(lines) + "\n")
    os.replace(temporary, path)


def move(run: Pass, slug: str, thread: str, kind: str = "tasks") -> None:
    """Make `thread` the slug's crew: its brief's `Thread:` line and its queue row's `thread`
    column, in one step under the queue's lock. Every launch jbus makes calls it once it has the
    thread, a resume's as much as a first one's."""
    queue.moved_thread(run.state, slug, thread, lambda: write_line(run, slug, thread, kind))


def repair(run: Pass) -> None:
    """Move each brief's `Thread:` line to its crew where a pass stopped before it wrote the line:
    no line, or one on an older launch's thread. A line on a thread no launch names is a hand
    resume's, and stays. Runs before anything reads the briefs for their thread."""
    directory = run.config.state_dir / "launches" / run.project.name
    for slug in sorted(path.name for path in directory.glob("*") if path.is_dir()):
        found = [r for _, r in newest(records(run, slug)) if r.get("thread")]
        if not found:
            continue
        line, there = _line(run, slug)
        if not there:
            continue
        kind = KINDS.get(str(found[-1].get("role") or queue.CREW), "tasks")
        thread = _answer(line, [jsettings.thread_id(str(r["thread"])) for r in found])
        if thread != line:
            move(run, slug, thread, kind)


@dataclass(frozen=True)
class Disagreement:
    """A row whose carriers name more than one thread: its brief's line, the thread of its newest
    launch, and its queue column, each as it stands, and the crew `crew` answers."""

    slug: str
    brief: str
    launched: str
    queue: str
    crew: str

    def line(self) -> str:
        return (
            f"{self.slug}: the crew is {self.crew or 'none'}; brief {self.brief or 'none'}, "
            f"launch {self.launched or 'none'}, queue {self.queue or 'none'}"
        )


def disagreements(run: Pass) -> list[Disagreement]:
    """Return each row of the queue whose carriers do not agree on its crew: a brief's line that
    is not the crew (a pass stopped before it moved it, or wrote none), or a queue column that is
    not. A launch record older than a hand resume's line is history, and no disagreement, and a row
    whose brief is gone has no line to disagree."""
    found = []
    for row in queue.load(run.state):
        slug = row["slug"]
        line, there = _line(run, slug)
        launches = _launches(run, slug, queue.role(row))
        column = jsettings.thread_id(str(row.get("thread") or ""))
        answer = _answer(line, launches)
        agrees = line == answer if there else not line
        if not answer or (agrees and column in ("", answer)):
            continue
        found.append(Disagreement(slug, line, launches[-1] if launches else "", column, answer))
    return found


def _run(_: argparse.Namespace, config: jbus.Config) -> int:
    from jbus.passes import Pass

    lines = [
        one.line()
        for project in config.projects
        for one in disagreements(Pass(config, project, datetime.now(UTC)))
    ]
    print("\n".join(lines) if lines else "none: every row's carriers name one crew thread")
    return 0


VERBS = (
    verbs.Verb(
        "crew-threads",
        "each row whose brief, launch records and queue column name more than one crew thread",
        verbs.nothing,
        _run,
    ),
)
