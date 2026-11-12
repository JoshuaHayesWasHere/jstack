"""`jbus poll`: one pass over every project, under one lock. `jbus --help` says what a pass does
(`jbus.cli`).

`poll` runs each project's `first_half`, the launches, the chores and each project's
`second_half`. Each half runs its fixed steps in order, and the steps that the modules of jbus
declare in their slots (`jbus.verbs.Step`). Importing this module imports every module of jbus,
to gather those steps and the chores, so only `jbus poll` and `jbus steps` import it.

Most of a pass is waiting on `gh` and `git`, so the projects' halves run side by side, each project
in a thread of its own with its own `Pass`, `Half` and `t3.Client`, and a project's steps keep their
order. All first halves end before the launches, the chores run alone, and `halves` keeps the order
of the config. What a project writes is under its own state directory, what the machine shares is
kept under a lock file (`jsettings.store.locked`), and a step marked `shared` decides from what
the machine shares, so it runs in one project at a time. A step marked `once` does the same work
for every project, so it runs in the first project's half alone. Each client's session ends with
the pass.

The pass times each of its parts, each step of each half and each project's whole half, into the
record's `Steps` (`jbus.record`), which `passes.jsonl` keeps. Timing a step changes nothing it does.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import jbus
from jbus import (
    alert,
    archived,
    dispatch,
    merge,
    passes,
    questions,
    queue,
    record,
    rotation,
    t3,
    threads,
    verbs,
    waiting,
    watch,
    work,
)
from jsettings import store

LAUNCH = "the launch"
FIRST = "first halves"
SECOND = "second halves"
_SHARED = threading.Lock()
"""Held while a step marked `shared` runs, so a project's step sees all that another project's
step recorded this pass."""


@dataclass
class Half:
    """A `Half` is the state of one pass that its steps, the dispatch and its second half read.

    `first_half` makes it when the pass starts, with the `Steps` its steps' seconds go to, under
    the part of the pass it is `within`. The pass fills it in as it runs its fixed steps in
    order, so a step reads what the fixed steps had set when its slot comes (`verbs.SLOTS`). `held`
    is the keys of the questions on record, or None where `questions.json` does not parse. `turns`
    is set when the project may launch: T3 Code and GitHub answered and the queue parses. `blind`
    marks a pass that cannot tell which slugs were removed, since `removed.json` does not parse.
    Such a pass reads no brief, acts on no thread or pull request, and leaves the list of what waits
    as it was. It still counts its crews at work.

    The second half fills in the rest. It records whether it `derived` the table and `read` every
    brief, the `states` it judged, and the `table` its steps read. When it derived the table anew,
    it records what `changed`. It keeps what `jmerge` said of the rows and that worded for the user
    (`merge.shown`), and what `stall.tell` and `waiting.keep` found (`roots`, `listed`).
    """

    run: passes.Pass
    client: t3.Client | None = None
    rows: list[queue.Row] | None = None
    seen: watch.Look = field(default_factory=watch.Look)
    said: merge.Said = field(default_factory=merge.Said)
    shown: merge.Said = field(default_factory=merge.Said)
    held: frozenset[str] | None = None
    turns: dispatch.Turns | None = None
    crews: set[int] = field(default_factory=set)
    blind: bool = False
    out: list[threads.Out] | None = None
    gone: frozenset[str] = frozenset()
    derived: bool = False
    read: bool = False
    states: watch.Judging | None = None
    table: list[queue.Row] | None = None
    changed: list[queue.Change] = field(default_factory=list)
    users: merge.Said = field(default_factory=merge.Said)
    roots: list[waiting.Item] = field(default_factory=list)
    listed: list[waiting.Item] | None = None
    times: record.Steps = field(default_factory=record.Steps)
    within: str = FIRST

    def timed(self, name: str) -> AbstractContextManager[None]:
        """Time a step of this half, under the part of the pass it runs in."""
        return self.times.timed(f"{self.within}/{name}")

    def answered(self) -> work.Answered:
        """Return which of T3 Code and GitHub answered the pass. When T3 Code is silent the
        pass does not ask GitHub, and when GitHub is silent there is no world."""
        if self.seen.world is not None:
            return work.Answered.BOTH
        return work.Answered.NEITHER if self.seen.out is None else work.Answered.T3


def steps(half: Half, slot: str) -> None:
    """Run a slot's steps by rank, each where the pass has its needs: `derive` judges the rows."""
    for step in RANKED[slot]:
        has = {
            "sight": not half.blind,
            "client": half.client is not None,
            "world": half.seen.world is not None,
            "rows": half.states is not None,
            "budget": not half.seen.held,
        }
        if not all(has[need] for need in step.needs):
            continue
        if step.once and half.run.project.name != half.run.config.projects[0].name:
            continue
        if step.shared:
            with _SHARED, half.timed(step.name):
                step.run(half)
        else:
            with half.timed(step.name):
                step.run(half)


def first_half(
    run: passes.Pass, client: t3.Client | None, times: record.Steps | None = None
) -> Half:
    """Run a project's pass up to any launch: merge, read, ask, and say what it found.

    This function runs the fixed steps of the pass in order, with a call to `steps` per slot. What
    it asks GitHub and T3 Code of the rows is asked of the crewmates' rows: a scout's row has no
    branch and no `crew: ` thread, and `jbus.scouts` launches it.
    """
    name = run.project.name
    half = Half(run, client) if times is None else Half(run, client, times=times)
    steps(half, "before-watch")
    with half.timed("merge.merge"):
        half.said = merge.merge(run)
    with half.timed("queue.load"):
        try:
            half.rows = queue.load(run.state)
        except queue.Unparsable as error:
            half.blind = error.path == queue.removed_path(run.state)
            run.gate(name, f"{error.path.name} does not parse", str(error.path))
    with half.timed("questions.read"):
        try:
            half.held = frozenset(one.key for one in questions.read(run.state))
        except questions.Unparsable:
            run.gate(name, "questions.json does not parse", str(questions.path(run.state)))
    crew = [row for row in half.rows or [] if queue.role(row) == queue.CREW]
    with half.timed("watch.look"):
        half.seen = watch.look(run, client, crew)
    if half.blind:
        half.seen = replace(half.seen, world=None)
    run.world = half.seen.world
    if half.seen.world is not None and client is not None:
        with half.timed("archived.ask"):
            archived.ask(run, client, half.seen.world, crew)
    steps(half, "tellers")
    rows, world = half.rows, half.seen.world
    if world is not None and client is not None:
        with half.timed("watch.gone"):
            half.gone = frozenset(
                row["slug"]
                for row in crew
                if watch.gone(run, world, row["slug"], dispatch.launched(run, row["slug"]))
            )
    steps(half, "after-expedite")
    if world is not None and client is not None and rows is not None:
        with half.timed("dispatch.turns"):
            half.turns = dispatch.turns(run, client, world, rows, half.seen.out or ())
    return half


def second_half(half: Half, client: t3.Client | None) -> None:
    """Run a project's pass after the launches: build the table, list what waits, send the wake.

    This function runs the fixed steps of the pass in order, with a call to `steps` per slot.
    """
    run, rows, world = half.run, half.rows, half.seen.world
    half.within = SECOND
    half.derived = world is not None and client is not None and rows is not None
    half.read = half.turns is not None and not half.turns.left
    half.table = rows
    steps(half, "derive")
    steps(half, "after-derive")
    steps(half, "close")
    with half.timed("alert.flush"):
        alert.flush(run)


def _whole(say: Callable[[str], None]) -> Callable[[str], None]:
    """Return `say` taking one line at a time, so no project's line lands inside another's."""
    saying = threading.Lock()

    def whole(line: str) -> None:
        with saying:
            say(line)

    return whole


def poll(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Run one pass over every project. A second pass that finds the lock held prints `busy`.

    Every project's first half runs before any launch, so the pass counts the crews at work
    across all of them. Every project's second half runs after the launches.

    When a project raises, the pass says so and keeps the error as the project's `last_error`. It
    still runs the other projects and writes the status file, then returns 1. It launches nothing,
    since it does not know how many crews that project has at work. A pass in which nothing raised
    ends the `pass` streak that `jbus alarm` counts, and the `stale` streak that
    `jbus alarm --stale` counts. A pass that cannot write its record says so and runs as usual.

    The pass ends by writing the status file (`record.write_status`).
    """
    say = _whole(say)
    with ExitStack() as lock:
        try:
            lock.enter_context(store.locked(config.state_dir, config.lock_path.name, wait=False))
        except BlockingIOError:
            say("busy")
            return 0
        client = None
        try:
            client = t3.Client(config.server, config.token_path)
            lock.callback(client.close)
        except jbus.Refused as error:
            say(str(error))
        now = now or datetime.now(UTC)
        last = jbus.read_json(config.status_path, {})
        raised: dict[str, str] = {}
        kept = record.Record(config, now)
        part = kept.steps.part

        def recorded(step: Callable[[], None]) -> None:
            try:
                step()
            except Exception as error:
                say(f"pass record failed: {alert.why(error, config)}")

        with part("start"):
            recorded(kept.start)

        def guarded(name: str, step: Callable[[], Any]) -> Any:
            try:
                return step()
            except Exception as error:
                raised[name] = alert.why(error, config)
                say(f"pass failed {name}: {raised[name]}")
                return None

        def first(project: jbus.Project) -> Half:
            with kept.steps.timed(f"{FIRST}/project {project.name}"):
                run = passes.Pass(config, project, now, say)
                record.heartbeat(run, last)
                own = t3.Client(config.server, config.token_path) if client else None
                if own is not None:
                    lock.callback(own.close)
                return first_half(run, own, kept.steps)

        def second(half: Half) -> None:
            with kept.steps.timed(f"{SECOND}/project {half.run.project.name}"):
                second_half(half, half.client)

        with part(FIRST):
            halves = passes.side_by_side(
                lambda p: guarded(p.name, lambda: first(p)), config.projects
            )
        halves = [half for half in halves if half is not None]
        if raised:
            say(f"wait: crews out not known ({', '.join(sorted(raised))}: the pass raised)")
        else:
            with part(LAUNCH):
                guarded(LAUNCH, lambda: rotation.share(config, halves, say))
        for chore in CHORES:
            with part(chore.name):
                guarded(chore.name, lambda chore=chore: chore.run(config, client, now, say))
        with part(SECOND):
            passes.side_by_side(
                lambda half: guarded(half.run.project.name, lambda: second(half)), halves
            )
        if not raised:
            with part(alert.PASS):
                guarded(alert.PASS, lambda: alert.recovered(config, say))
        with part("status"):
            record.write_status(config, now, last, raised, say)
        recorded(lambda: kept.end(record.saw(halves), record.silent(halves)))
    return 1 if raised else 0


VERBS = (
    verbs.Verb(
        "poll", "one pass over every project", verbs.nothing, lambda _, config: poll(config)
    ),
)
RANKED = verbs.ranked(jbus.__path__)
CHORES = verbs.chores(jbus.__path__)
