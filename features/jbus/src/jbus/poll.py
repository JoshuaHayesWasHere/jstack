"""`jbus poll`: one pass over every project, under one lock. `jbus --help` says what a pass does
(`jbus.cli`).

`poll` runs each project's `first_half`, the launches, the chores and each project's
`second_half`. Each half runs its fixed steps in order, and the steps that the modules of jbus
declare in their slots (`jbus.verbs.Step`). Importing this module imports every module of jbus,
to gather those steps and the chores, so only `jbus poll` and `jbus steps` import it.
"""

from __future__ import annotations

import fcntl
from collections.abc import Callable
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
    signin,
    t3,
    threads,
    verbs,
    waiting,
    wake,
    watch,
    work,
)

LAUNCH = "the launch"


@dataclass
class Half:
    """A `Half` is the state of one pass that its steps, the dispatch and its second half read.

    `first_half` makes it when the pass starts. The pass fills it in as it runs its fixed steps in
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
        if all(has[need] for need in step.needs):
            step.run(half)


def first_half(run: passes.Pass, client: t3.Client | None) -> Half:
    """Run a project's pass up to any launch: merge, read, ask, and say what it found.

    This function runs the fixed steps of the pass in order, with a call to `steps` per slot. What
    it asks GitHub and T3 Code of the rows is asked of the crewmates' rows: a scout's row has no
    branch and no `crew: ` thread, and `jbus.scouts` launches it.
    """
    name = run.project.name
    half = Half(run, client)
    steps(half, "before-watch")
    line = signin.expiring(run.config, run.now)
    if line and run.condition(name, line, key=f"sign-in {run.day}"):
        wake.notify(f"{name}: {line}")
    half.said = merge.merge(run)
    try:
        half.rows = queue.load(run.state)
    except queue.Unparsable as error:
        half.blind = error.path == queue.removed_path(run.state)
        run.gate(name, f"{error.path.name} does not parse", str(error.path))
    try:
        half.held = frozenset(one.key for one in questions.read(run.state))
    except questions.Unparsable:
        run.gate(name, "questions.json does not parse", str(questions.path(run.state)))
    crew = [row for row in half.rows or [] if queue.role(row) == queue.CREW]
    half.seen = watch.look(run, client, crew)
    if half.blind:
        half.seen = replace(half.seen, world=None)
    run.world = half.seen.world
    if half.seen.world is not None and client is not None:
        archived.ask(run, client, half.seen.world, crew)
    steps(half, "tellers")
    rows, world = half.rows, half.seen.world
    if world is not None and client is not None:
        half.gone = frozenset(
            row["slug"]
            for row in crew
            if watch.gone(run, world, row["slug"], dispatch.launched(run, row["slug"]))
        )
    steps(half, "after-expedite")
    if world is not None and client is not None and rows is not None:
        half.turns = dispatch.turns(run, client, world, rows, half.seen.out or ())
    return half


def second_half(half: Half, client: t3.Client | None) -> None:
    """Run a project's pass after the launches: build the table, list what waits, send the wake.

    This function runs the fixed steps of the pass in order, with a call to `steps` per slot.
    """
    run, rows, world = half.run, half.rows, half.seen.world
    half.derived = world is not None and client is not None and rows is not None
    half.read = half.turns is not None and not half.turns.left
    half.table = rows
    steps(half, "derive")
    steps(half, "after-derive")
    steps(half, "close")
    sent = alert.flush(run, client)
    if sent:
        run.say(f"woke {run.project.name}: {sent} events")


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

    When the config still has a key that nothing reads, each pass says so in one line until the
    user removes the key. The pass ends by writing the status file (`record.write_status`).
    """
    config.state_dir.mkdir(parents=True, exist_ok=True)
    with open(config.lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say("busy")
            return 0
        client = None
        try:
            client = t3.Client(config.server, config.token_path)
        except jbus.Refused as error:
            say(str(error))
        if config.ignored:
            say(
                f"ignored: {config.config_dir / 'config.toml'} still has "
                f"{', '.join(config.ignored)}: jbus reads none of them, remove them"
            )
        now = now or datetime.now(UTC)
        last = jbus.read_json(config.status_path, {})
        raised: dict[str, str] = {}
        kept = record.Record(config, now)

        def recorded(step: Callable[[], None]) -> None:
            try:
                step()
            except Exception as error:
                say(f"pass record failed: {alert.why(error, config)}")

        recorded(kept.start)

        def guarded(name: str, step: Callable[[], Any]) -> Any:
            try:
                return step()
            except Exception as error:
                raised[name] = alert.why(error, config)
                say(f"pass failed {name}: {raised[name]}")
                return None

        def first(project: jbus.Project) -> Half:
            run = passes.Pass(config, project, now, say)
            record.heartbeat(run, last)
            return first_half(run, client)

        halves = [guarded(p.name, lambda p=p: first(p)) for p in config.projects]
        halves = [half for half in halves if half is not None]
        if raised:
            say(f"wait: crews out not known ({', '.join(raised)}: the pass raised)")
        else:
            guarded(LAUNCH, lambda: rotation.share(config, halves, say))
        for chore in CHORES:
            guarded(chore.name, lambda chore=chore: chore.run(config, client, now, say))
        for half in halves:
            guarded(half.run.project.name, lambda half=half: second_half(half, client))
        if not raised:
            alert.recovered(config, [half.run for half in halves], guarded, raised)
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
