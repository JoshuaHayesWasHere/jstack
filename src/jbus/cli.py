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
Beside the status file is the record of the pass
(`record`), written when the pass starts and again when it ends.
No model reads anything.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jbus
from jbus import (
    alert,
    dispatch,
    expedite,
    leftover,
    merge,
    mirror,
    project,
    questions,
    queue,
    record,
    rotation,
    signin,
    stall,
    t3,
    threads,
    verbs,
    view,
    waiting,
    wake,
    watch,
    word,
    work,
)

SNAPSHOT_DAYS = 14
ALARM = "the last pass did not finish (see journalctl --user -u jbus)"
LAUNCH = "the launch"
REMINDER = "the sign-in reminder"
RETIRED, EXEC_SENT = "exec-webhook", "exec-sent.json"


def snapshot(run: wake.Pass, rows: list[queue.Row] | None) -> str:
    parts = [queue.render(rows) if rows is not None else "queue.json does not parse\n"]
    since = (run.now - timedelta(days=SNAPSHOT_DAYS)).timestamp()
    briefs = [p for p in (run.home / "tasks").glob("*.md") if p.stat().st_mtime >= since]
    for path in sorted(briefs, key=lambda p: p.stat().st_mtime, reverse=True):
        text = path.read_text(errors="replace")
        title = text.splitlines()[0] if text.strip() else f"# {path.stem}"
        parts.append(f"\n{title}\n{mirror.last_result(text) or 'no Result'}\n")
    return "".join(parts)


def expiring(config: jbus.Config, now: datetime) -> str:
    """What is said of a sign-in within `warn_days` of running out, or nothing."""
    expires = t3.expiry(config.token_path)
    if expires is None or expires - now > timedelta(days=config.warn_days):
        return ""
    user = config.user
    return f"T3 sign-in expires {user.day(expires)} {user.word(expires)}, run jbus t3 login"


def _hook(config: jbus.Config, box: wake.Box, route: wake.Route, key: str) -> dict[str, Any]:
    """What the status file says of one webhook of a project: its streak, its last error and
    what waits in its outbox."""
    failing = alert.streak(config.state_dir, key)
    return {
        "failed_wakes": failing.count if failing else 0,
        "last_error": box.marks(route).get("last_error", ""),
        "outbox": box.waiting(route),
    }


def status(config: jbus.Config, now: datetime) -> dict[str, Any]:
    """What the status file holds: read back from what the pass left, and the homes not on
    the bus, which no pass leaves (`project.missing`)."""
    expires = t3.expiry(config.token_path)
    projects = {}
    for one in config.projects:
        box = wake.Box(config.state(one), one, config.webhook, config.blocking)
        marks = box.marks()
        projects[one.name] = {
            **_hook(config, box, box.routes[0], alert.webhook(one.name)),
            "sign_in": expiring(config, now),
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
    }


@dataclass
class Half:
    """What a project's first half leaves: for its steps, the dispatch, and its second half.

    It is made when the pass starts and filled in as the spine runs, so a step reads what
    the spine had by its slot (`verbs.SLOTS`). `held` is the keys of the questions on
    record, or None where `questions.json` does not parse. `turns` is there when the
    project may launch: T3 Code and GitHub answered and the queue parses. `blind` is a pass
    that cannot tell which slugs were removed, since `removed.json` does not parse: it reads
    no brief, acts on no thread or pull request, and leaves the list of what waits as it
    was. Its crews out are still counted.
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


def steps(half: Half, slot: str) -> None:
    """Run the steps of a slot by rank, each one whose needs the pass has."""
    has = {
        "sight": not half.blind,
        "client": half.client is not None,
        "world": half.seen.world is not None,
    }
    for step in RANKED[slot]:
        if all(has[need] for need in step.needs):
            step.run(half)


def first_half(run: wake.Pass, client: t3.Client | None) -> Half:
    """What a project's pass does before any launch: merge, read, ask, and say what it found.

    The spine is written out here, and the steps of each slot run where it is.
    """
    name = run.project.name
    half = Half(run, client)
    steps(half, "before-watch")
    line = expiring(run.config, run.now)
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


def share(config: jbus.Config, halves: list[Half], say: Callable[[str], None]) -> None:
    """Launch across the projects: one count of the crews out, and the free slots in turns.

    The turns start at the project the rotation file names. With the crews out of any
    project not known, the count is not known, and nothing is launched anywhere.
    """
    start = rotation.start(config)
    turns = [half.turns for half in halves[start:] + halves[:start] if half.turns]
    out = [half.seen.out for half in halves]
    known = [count for count in out if count is not None]
    for half in halves:
        if half.seen.out is None:
            say(f"wait: crews out not known ({half.run.project.name}: {half.seen.why})")
    slots = config.max_running - sum(known) if len(known) == len(out) else None
    made = dispatch.dispatch(turns, slots)
    if made:
        rotation.keep(config, made[-1])


def second_half(half: Half, client: t3.Client | None) -> None:
    """What a project's pass does after the launches: the table, what waits, and the wake."""
    run, rows, world = half.run, half.rows, half.seen.world
    name = run.project.name
    derived = world is not None and client is not None and rows is not None
    read = half.turns is not None and not half.turns.left
    states = judged(half, client) if rows is not None and not half.blind else None
    if derived and states is not None:
        waits = watch.waits(run, half.said, merge.home_thread(run))
        unread = watch.unread(run, read)

        def facts(row: queue.Row) -> queue.Row:
            slug = row["slug"]
            launched = dispatch.launched(run, slug)
            found = watch.status(run, world, slug, states.of(row, launched), launched)
            return {**found, "why": watch.why(run, row, found, waits, unread)}

        at = run.now.astimezone(UTC).isoformat(timespec="seconds")
        rows, changed = queue.derive(run.state, facts, run.user.stamp(run.now), at)
        if changed:
            line = f"queue {run.project.name}: the table changed"
            run.box.send("", "queue", line, queue.changes(changed))
        leftover.tell(run, client, world, rows, half.out)
        stall.unclosed(run, world, rows)
        unplaced(half, client, rows, states)
    if states is not None:
        keep_work(half, rows or [], states)
    users = half.said.crews(half.crews)
    roots = stall.tell(run, client, world, rows, users)
    listed = None
    if not half.blind:
        listed = waiting.keep(run, world, rows, users, roots, derived=derived, read_all=read)
    waiting.cadence(run, listed, rows, world)
    if world is not None:
        run.box.began()
    day = run.box.snapshot_due(run.user.local(run.now))
    if day:
        line = f"snapshot {run.project.name}: {day}"
        run.box.send("", "snapshot", line, snapshot(run, rows), cap=wake.SNAPSHOT_CAP)
        run.box.snapshot_sent(day)
        if world is not None:
            run.box.prune(
                {
                    slug
                    for slug, pull in world.merged.items()
                    if slug not in world.open
                    and run.now - watch.when(pull["mergedAt"]) >= wake.PRUNE_AFTER
                }
            )
        run.box.forget(run.now - wake.LOG_KEEP)
    owed = run.box.sweep_owed()
    if owed:
        ran, how = merge.sweep(run)
        how = f"{owed}: {how}" if ran else f"{owed}: {how}, retrying next pass"
        if not ran:
            run.say(f"wait {name}: {how}")
        run.box.swept(how, ran)
    sent = alert.flush(run)
    if sent:
        run.say(f"woke {name}: {sent} events")


def answered(half: Half) -> work.Answered:
    """Which of T3 Code and GitHub answered the pass. With T3 Code silent GitHub is not
    asked, and with GitHub silent there is no world."""
    if half.seen.world is not None:
        return work.Answered.BOTH
    return work.Answered.NEITHER if half.seen.out is None else work.Answered.T3


def judged(half: Half, client: t3.Client | None) -> watch.Judging:
    """The state of each row of the queue, judged once (`work.judge`). A row waits on
    another until that one is merged or ended `done`, by the rule `dispatch` launches by
    (`watch.final`).

    With GitHub silent and T3 Code answering, the steps that list the threads out did not
    run, since they act on a world: the threads out are listed here as that step lists them,
    and `stall.hung` reads them, so a thread's liveness is still judged and a hang told.
    """
    run, world, rows = half.run, half.seen.world, half.rows or []
    if world is None and half.out is None and half.seen.out is not None and client is not None:
        half.out = threads.out(run, client, stall.watched(run))
        stall.hung(run, half.out)
    said = dict(watch.waits(run, half.said, merge.home_thread(run)).said) if world else {}
    if half.said.failed:
        for row in rows:
            number = str(row.get("pr", "")).removeprefix("#")
            if row.get("status") == "pr" and number and number not in said:
                said[number] = row.get("why", "")
    last = work.last(run.state)
    seen = watch.Seen(half.out, half.gone, said, watch.final(run, world, rows), answered(half))
    return watch.Judging(run, world, seen, last)


def unplaced(half: Half, client: t3.Client, rows: list[queue.Row], states: watch.Judging) -> None:
    """Tell the home of each row whose pull request is open and on no step (`merge.unplaced`),
    by what `jmerge` said of it in this pass."""
    run, world = half.run, half.seen.world
    for row in rows:
        slug = row["slug"]
        pull = (world.open if world else {}).get(slug)
        if pull is None:
            continue
        number = str(pull.get("number", ""))
        said = states.seen.said.get(number, "")
        home = leftover.home_of(run.home, watch.brief_of(run, slug))
        merge.unplaced(run, client, slug, number, said, word.home(home))


def keep_work(half: Half, rows: list[queue.Row], states: watch.Judging) -> None:
    """Write `work.json`: the state of every row, and of every thread out that is no row's,
    each with who holds it (`work.holder`). With no list of the threads out, the threads are
    the last pass's, not confirmed."""
    run = half.run
    held = leftover.read(run.state)
    listed = []
    for row in rows:
        slug = row["slug"]
        state = states.of(row, dispatch.launched(run, slug))
        record = held.get(slug)
        home = bool(record and not record.busy and not leftover.his(record, run.now))
        after = watch.after_merge(mirror.last_result(watch.brief_of(run, slug)))
        line = work.entry(
            state,
            work.holder(state, home=home, after=after),
            key=slug,
            kind="row",
            slug=slug,
            thread=row.get("thread", ""),
            pr=row.get("pr", ""),
        )
        listed.append(line)
    listed += watch.judged(run, half.out, {row["slug"] for row in rows}, answered(half))
    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    work.write(run.state, at, answered(half), listed)


def saw(halves: list[Half]) -> dict[str, dict[str, Any]]:
    """The open rows and the threads out of each project whose pass had answers from T3
    Code and GitHub."""
    found = {}
    for half in halves:
        run, world, rows = half.run, half.seen.world, half.rows
        if world is None or rows is None:
            continue
        found[run.project.name] = {
            "rows": record.rows(world, rows, half.out, half.gone),
            "threads": record.threads(half.out),
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


def _why(error: Exception, *hooks: jbus.Project | jbus.Hook) -> str:
    """An exception as one line, for the journal and the status file.

    An error from a webhook URL that cannot be used quotes it, whole or in part, so what
    is secret of each hook is taken out (`jbus.secrets`).
    """
    said = " ".join(f"{type(error).__name__}: {error}".split())
    return wake.cut(jbus.redact(said, jbus.secrets(*hooks, part=2), "[webhook]"), 300)


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


def poll(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """One pass over every project. A second pass that finds the lock held prints `busy`.

    Every project's first half runs before any launch, so the crews out are counted over
    all of them, and every project's second half runs after the launches.

    A project that raises is said, kept as its `last_error`, and does not end the pass: the
    others still run and the status file is still written. The answer is then 1. Nothing
    is launched in such a pass, since that project's crews out are not known. A pass in
    which nothing raised ends the `pass` streak that `jbus alarm` counts. A record of the
    pass that cannot be written is said, and the pass does all it does with one.

    A config that still has a key nothing reads is said in one line, on each pass until
    the key is removed. The homes that have no project in the config are said in one line
    too, on the pass their list changes (`project.missing`). What the copy to Exec left
    behind goes here too: its streak, which nothing else would end, and each project's list
    of copies owed.
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
        alert.retire(config.state_dir, RETIRED)
        for one in config.projects:
            with contextlib.suppress(OSError):
                (config.state(one) / EXEC_SENT).unlink()
        now = now or datetime.now(UTC)
        last = jbus.read_json(config.status_path, {})
        raised: dict[str, str] = {}
        kept = record.Record(config, now)

        def recorded(step: Callable[[], None]) -> None:
            try:
                step()
            except Exception as error:
                say(f"pass record failed: {_why(error, *config.hooks())}")

        recorded(kept.start)

        def guarded(name: str, step: Callable[[], Any]) -> Any:
            try:
                return step()
            except Exception as error:
                raised[name] = _why(error, *config.hooks())
                say(f"pass failed {name}: {raised[name]}")
                return None

        def first(project: jbus.Project) -> Half:
            run = wake.Pass(config, project, now, say)
            heartbeat(run, last)
            return first_half(run, client)

        halves = [guarded(p.name, lambda p=p: first(p)) for p in config.projects]
        halves = [half for half in halves if half is not None]
        if raised:
            say(f"wait: crews out not known ({', '.join(raised)}: the pass raised)")
        else:
            guarded(LAUNCH, lambda: share(config, halves, say))
        guarded(REMINDER, lambda: signin.remind(config, now))
        for half in halves:
            guarded(half.run.project.name, lambda half=half: second_half(half, client))
        if not raised:
            recovered = alert.ok(config.state_dir, alert.PASS, user=config.user)
            for half in halves:
                name = half.run.project.name
                guarded(name, lambda half=half: alert.deliver(half.run, recovered))
            if recovered and not raised:
                alert.told(config.state_dir, alert.PASS)
        report = status(config, now)
        if report["homes_off_bus"] != last.get("homes_off_bus", []):
            say(f"homes not on the bus: {', '.join(report['homes_off_bus']) or 'none'}")
        for name, why in raised.items():
            if name in report["projects"]:
                report["projects"][name]["last_error"] = why
        jbus.write_json(config.status_path, report, mode=0o600)
        recorded(lambda: kept.end(saw(halves), silent(halves)))
    return 1 if raised else 0


def alarm(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Count a pass that did not finish. The third in a row alerts every project, once.

    The alert waits in the outbox like any other event, and what waits is flushed each time,
    so one the webhook did not take goes with the next alarm or the next pass that ends.
    The desk is told too, once: what ends a pass may be the webhook, or a project's state.
    The streak is marked alerted after the desk and the projects were told, so an alarm
    that is stopped before then alerts again on the next one.
    """
    now = now or datetime.now(UTC)
    line = alert.failed(config.state_dir, alert.PASS, ALARM, now=now, user=config.user)
    failing = alert.streak(config.state_dir, alert.PASS)
    say(f"pass failed: {failing.count if failing else 1} in a row")
    if line:
        wake.notify(line)
    code = 0
    for one in config.projects:
        try:
            run = wake.Pass(config, one, now, say)
            alert.deliver(run, line, desk=False)
            alert.flush(run)
            if line:
                say(f"alert {'waits' if run.box.waiting() else 'sent'}: {one.name}")
        except Exception as error:
            say(f"alarm failed {one.name}: {_why(error, one)}")
            code = 1
    if line:
        alert.told(config.state_dir, alert.PASS)
    return code


def _port(shown: argparse.ArgumentParser) -> None:
    shown.add_argument("--port", type=int, default=view.PORT, help="the one port it listens on")


VERBS = (
    verbs.Verb(
        "poll", "one pass over every project", verbs.nothing, lambda _, config: poll(config)
    ),
    verbs.Verb(
        "alarm",
        "count a pass that did not finish: the third in a row alerts",
        verbs.nothing,
        lambda _, config: alarm(config),
    ),
    verbs.Verb(
        "view",
        "serve the bus as a page, read-only",
        _port,
        lambda args, _: view.doors(args.port).serve(),
        abbrev=False,
        config=False,
    ),
)
DECLARED = verbs.declared(jbus.__path__)
RANKED = verbs.ranked(jbus.__path__)


def _words_left(args: argparse.Namespace, extra: list[str]) -> list[str]:
    """The user's words that Python 3.12.3's argparse left over, and what is left after them.

    A verb's `words` follow its number and its options. That argparse fills `words` with
    nothing when it reads the number, and hands the words back unparsed; later 3.12 releases
    and 3.13 read them as words. So where `words` came back empty, every plain string left
    over is a word, and so is everything after `--`."""
    if getattr(args, "words", None) != [] or not extra:
        return extra
    words: list[str] = []
    left: list[str] = []
    after = False
    for given in extra:
        if after or not given.startswith("-"):
            words.append(given)
        elif given == "--":
            after = True
        else:
            left.append(given)
    args.words = words
    return left


def _usage(parser: argparse.ArgumentParser) -> str:
    """The parser's own usage, as Python 3.13 and later print it: 3.12 puts the ` ...` after
    the verbs on a line of its own."""
    usage = parser.format_usage().removeprefix("usage: ").rstrip("\n")
    return re.sub(r"\n *\.\.\.$", " ...", usage)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jbus", description=__doc__, allow_abbrev=False)
    parser.add_argument("--project", help="the project's name in the config, when it has several")
    commands = parser.add_subparsers(dest="command", required=True)
    for verb in DECLARED.values():
        verb.arguments(commands.add_parser(verb.name, help=verb.help, allow_abbrev=verb.abbrev))
    parser.usage = _usage(parser)
    args, extra = parser.parse_known_args(argv)
    extra = _words_left(args, extra)
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
