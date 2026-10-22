"""The one entry point: `jbus poll`, `jbus queue show|add|approve|hold|remove|apply`, `jbus
plan [close <entry>]`, `jbus gate <slug>`, `jbus answer <number>`, `jbus done <slug>`, `jbus
status`, `jbus events`, `jbus digest`, `jbus alarm`, `jbus view`, `jbus word`, `jbus project
add`, and `jbus t3 login|launch-test`.

`jbus poll` is one pass over every project in the config, under one lock: it runs `jmerge`
where the home is off, reads what the threads wrote down, asks T3 Code and GitHub what is
out, sends a line for each finding, ties each crew to its thread (the link, the relay and
the settle), tells a crew whose pull request `jmerge` calls stale or conflicting to rebase,
and one whose pull request is short of something it can fix what to do (`expedite`),
launches the rows of the queue that were approved, rewrites the table's derived columns
(with why each row waits, and a line for each change of status), says what waits on the user
(`stall`), again each hour, and rewrites the one list of it (`waiting`).
A row that ended with something left is sent to its home to close, once (`leftover`): it
waits on that home, and on the user only where it has no home or the home did not close it.
The launches come after every project was asked what is out: `max_running` caps the crews
out across all of them, and the free slots go to the projects in turn (`rotation`).
A gate a thread pipes to `jbus gate` is a question with a number (`questions`): it waits on
the user until `jbus answer` closes it, and a pass carries an answer that is not the default
to the thread that asked.
Everything it finds is an event with a loudness (`wake.LOUDNESS`), and the project's
webhook is posted only what the user must act on: a new question, a hold or an approval
that is theirs, an alert, a stall. Everything else is quiet: it is in the log, which
`jbus events` prints and the view shows. A failure that repeats is told once, and once
when it ends (`alert`).
`jbus word` is the user's word down to a home: it keeps what he said for one project or for
all, and sends it to the thread in each home's `home-id` as a queued message, at once and
then on each pass until it went (`word`). It is no event, so no webhook is posted it.
Once a day it asks `jmerge` what a sweep would remove, and again on each pass until
`jmerge` has run. Each pass ends by rewriting the status file, which `jbus status` prints:
what a webhook that is down cannot say.
`jbus view` is no pass: it is a server that shows what the passes left, and it reads no
config (`jbus.view`).
`jbus project add` is no pass either: it adds one project's table to the config, and the
next pass loads it (`jbus.project`).
A scratch home of the config is no project of the pass, and no repo step is run for it
(`jbus.load`): its words go to its thread in a chore of the pass (`word.scratch`).
Beside the status file is the record of the pass
(`record`), written when the pass starts and again when it ends.
No model reads anything.
"""

from __future__ import annotations

import fcntl
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import jbus
from jbus import (
    alert,
    archived,
    dispatch,
    expedite,
    merge,
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
    """A `Half` is the state of a project's pass that its steps, the dispatch and its second
    half read.

    `first_half` makes it when the pass starts. The pass fills it in as it runs its fixed steps in
    order, so a step reads what the fixed steps had set when its slot comes (`verbs.SLOTS`). `held`
    is the keys of the questions on record, or None where `questions.json` does not parse. `turns`
    is set when the project may launch: T3 Code and GitHub answered and the queue parses. `blind`
    marks a pass that cannot tell which slugs were removed, since `removed.json` does not parse.
    Such a pass reads no brief, acts on no thread or pull request, and leaves the list of what waits
    as it was. It still counts its crews at work.

    The second half fills in the rest. It records whether it `derived` the table and `read`
    every brief, the `states` it judged, and the `table` its steps read. When it derived the
    table anew, it records what `changed`. It keeps what `jmerge` said, worded for the user
    (`users`), and what `stall.tell` and `waiting.keep` found (`roots`, `listed`).
    """

    run: wake.Pass
    client: t3.Client | None = None
    rows: list[queue.Row] | None = None
    seen: watch.Look = field(default_factory=watch.Look)
    said: merge.Said = field(default_factory=merge.Said)
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
    """Run the steps of a slot by rank, each step only when the pass has what that step
    needs. A step of `derive` judges the rows that the later steps need."""
    for step in RANKED[slot]:
        has = {
            "sight": not half.blind,
            "client": half.client is not None,
            "world": half.seen.world is not None,
            "rows": half.states is not None,
        }
        if all(has[need] for need in step.needs):
            step.run(half)


def first_half(run: wake.Pass, client: t3.Client | None) -> Half:
    """Run a project's pass up to any launch: merge, read, ask, and say what it found.

    This function runs the fixed steps of the pass in order, with a call to `steps` per slot.
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
    half.seen = watch.look(run, client, half.rows or [])
    if half.blind:
        half.seen = watch.Look(out=half.seen.out, why=half.seen.why)
    if half.seen.world is not None and client is not None:
        archived.ask(run, client, half.seen.world, half.rows or [])
    steps(half, "tellers")
    rows, world = half.rows, half.seen.world
    if world is not None and client is not None:
        half.gone = frozenset(
            row["slug"]
            for row in rows or []
            if watch.gone(run, world, row["slug"], dispatch.launched(run, row["slug"]))
        )
        half.crews = expedite.tell(run, client, world, half.said)
    else:
        half.crews = expedite.told(run, half.said)
    steps(half, "after-expedite")
    if world is not None and client is not None and rows is not None:
        half.turns = dispatch.turns(run, client, world, rows)
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
    half.users = half.said.crews(half.crews)
    steps(half, "close")
    sent = alert.flush(run)
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
                say(f"pass record failed: {alert.why(error, *config.hooks())}")

        recorded(kept.start)

        def guarded(name: str, step: Callable[[], Any]) -> Any:
            try:
                return step()
            except Exception as error:
                raised[name] = alert.why(error, *config.hooks())
                say(f"pass failed {name}: {raised[name]}")
                return None

        def first(project: jbus.Project) -> Half:
            run = wake.Pass(config, project, now, say)
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
DECLARED = verbs.declared(jbus.__path__)
RANKED = verbs.ranked(jbus.__path__)
CHORES = verbs.chores(jbus.__path__)


def main(argv: list[str] | None = None) -> int:
    parser = verbs.parser(DECLARED, __doc__)
    args, extra = parser.parse_known_args(argv)
    extra = verbs.words_left(args, extra)
    for given in extra:
        column = given.lstrip("-").split("=")[0].replace("-", "_")
        if column in queue.DERIVED:
            print(f"refused: {column} is derived from T3 Code and GitHub, and no command writes it")
            return 2
    if extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    verb = DECLARED[args.command]
    try:
        return verb.run(args, jbus.load() if verb.config else None)
    except (jbus.Refused, t3.T3Error) as error:
        print(error)
        return 1
