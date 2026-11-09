"""Declare `jbus queue`: the verbs on the queue's table, and what they ask of the other modules.

The table and its verbs are in `jbus.queue`, which calls no other module for a fact. A
removal or an approval needs facts from T3 Code, GitHub, the launch records and the words that
jbus recorded, and `jbus.queue` gets them as a `queue.Asks`. `_asks` builds one for a project
with the modules that read those facts, and each of those modules imports the queue. So this
module, which imports all of them, declares the verb, and `jbus.queue` does not.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
from jbriefs import chains
from jbriefs import parse as briefs
from jbus import (
    acts,
    blockers,
    boxes,
    dispatch,
    item,
    needs,
    party,
    passes,
    plan,
    questions,
    queue,
    scouts,
    t3,
    verbs,
    waiting,
    wake,
    watch,
    word,
)
from jmerge import judgement
from jmerge.asked import Silent
from jsettings import brief as brief_head


def _asks(config: jbus.Config, project: jbus.Project) -> queue.Asks:
    """Return what `queue remove` and `queue approve` ask, and the one quiet event a removal
    sends.

    `said` returns the words an approval names: a word of the project's `acts.jsonl`, the
    answer of a closed question of its `questions.json`, a message read from T3 Code, the
    user's answer to a question box read from T3 Code and its store. A follow-up's go reads no
    file of the home: jbus knows the rule by what it says.
    `entry_go` reads the go of a row's plan entry (`plan.holding`).

    `out` asks T3 Code and GitHub now for a thread that is at work, `crew: <slug>` or
    `scout: <slug>`, an open pull request, or a merged one. A thread that ended or settled is
    not out. Where `out` cannot ask either of them, it says so, and the answer is unknown.
    `launched` reads the launch records. A record at `intent` is a launch that T3 Code has not
    answered yet. A record written after this call began means that a pass launched the slug
    after `out` asked. The event carries the row as it was, and jbus logs it and sends it to no
    thread.
    """
    run = passes.Pass(config, project, datetime.now(UTC))
    began = time.time()

    def launched(slug: str) -> str:
        for path, kept in dispatch.records(run, slug):
            if kept.get("state") == "intent":
                return f"{slug} is out: its launch has no answer yet ({path})"
            try:
                new = path.stat().st_mtime >= began
            except OSError:
                continue
            if new:
                return f"{slug} is out: a pass launched it just now"
        return ""

    def told(move: dict[str, Any]) -> None:
        slug = move["slug"]
        line = f"queue {project.name}: removed {slug}, {move['said']} by {move['by']}"
        run.box.send(slug, "queue", line, queue.render([move["row"]]))
        blockers.forgo(run, move)

    def out(slug: str) -> str:
        scout = f"{scouts.TITLE}{slug}"
        try:
            client = t3.Client(config.server, config.token_path)
            listed = watch.crew_threads(client, project.project_id, f"{watch.TITLE}{slug}")
            scouting = t3.listed(client, project.project_id, titleContains=scout)
        except (jbus.Refused, t3.T3Error) as error:
            why = str(error).removeprefix("refused: ")
            asked = f"T3 Code could not be asked whether {slug}'s thread is out"
            raise jbus.Refused(f"refused: {asked} ({why})") from error
        working = [t for t in listed if watch.at_work([t], f"{watch.TITLE}{slug}")] + [
            t for t in scouting if str(t.get("title", "")).strip() == scout and watch.at_work([t])
        ]
        if working:
            thread = working[0]
            return f"{slug} is out: its thread {thread['threadId']} is {thread['status']}"
        for state, said in (
            ("open", "{slug} is out: its pull request #{number} is open"),
            ("merged", "{slug} merged as #{number}, and a merged row stays"),
        ):
            try:
                found = watch.pulls(run, state, "number", "--head", slug, "--limit", "1")
            except Silent as silent:
                asked = f"GitHub could not be asked whether {slug} has a pull request"
                raise jbus.Refused(f"refused: {asked}{silent}") from silent
            if found:
                return said.format(slug=slug, number=found[0]["number"])
        return ""

    def said(basis: str, ref: str) -> queue.Said:
        if basis == "message":
            return t3.heard(config, ref)
        if basis == queue.PICK:
            return boxes.picked(config, ref)
        return (word.basis if basis == "word" else questions.basis)(run.state, ref)

    goes = plan.entry_go(run.state, config.home(project))
    return queue.Asks(out, launched, told, said, goes)


READS = ("show", "verify", "check")
"""The verbs of `jbus queue` that change nothing, and so work on a closed project too."""


def _queue(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project, closed=args.verb in READS)
    state = config.state(project)
    if args.verb == "apply":
        asks = _asks(config, project)
        text = verbs.piped("queue apply", "the verbs", "")
        releases = []
        try:
            for _, verb in queue.parse(text):
                if isinstance(verb, queue.Add):
                    releases.append(blockers.admit(config, project, verb.slug, verb.text))
            run = passes.Pass(config, project, datetime.now(UTC))
            print("\n".join(acts.batch(run, asks, args, text)))
        except BaseException:
            for release in releases:
                release()
            raise
        for _, verb in queue.parse(text):
            if isinstance(verb, queue.Add):
                _warn(config, project, verb.slug, verb.text)
            elif isinstance(verb, (queue.Approve, queue.Remove)):
                acted = "go" if isinstance(verb, queue.Approve) else "remove"
                waiting.acted(run, acted, verb.slug)
        return 0
    if args.verb == "verify":
        return _verify(state, args.slug, args.brief)
    if args.verb == "check":
        return _check(config, project, args.slug, args.handed)
    if args.verb == "add":
        depends = queue.slugs(args.depends or "")
        text = verbs.piped("queue add", "the brief")
        home_fault = queue.owned(
            config.home(project), project.name, args.slug, text, args.adder, args.handed
        )
        release = blockers.admit(config, project, args.slug, text)
        try:
            named = _item(state, args.slug, args.item or "")
            after = queue.slugs(args.merge_after or "")
            asks = _asks(config, project)
            said, *ruled = queue.add(
                state,
                args.slug,
                args.priority,
                depends,
                text,
                args.entry or "",
                named,
                after,
                config.user,
                asks,
                home_fault=home_fault,
                message=args.message or "",
            )
        except BaseException:
            release()
            raise
        if said.endswith((queue.GO_HOLDS, queue.GO_VOID)) or queue.TAKEN in said:
            print(said)
        for line in ruled:
            print(line)
        if args.message:
            _went(config, project, args.slug, text, args.message, ruled)
        _warn(config, project, args.slug, text)
        row = queue.fresh(state, args.slug)
        if row is not None:
            by = queue.who(queue.runner())
            box = wake.Box(state, project)
            item.link(state, box, row, args.item or "", by, config.user.user)
    elif args.verb == "approve":
        run = passes.Pass(config, project, datetime.now(UTC))
        made = acts.go(args, run, _asks(config, project))
        _, *ruled = made.line.split("\n")
        for line in [made.line] if made.outcome in ("gated", "noop") else ruled:
            print(line)
    elif args.verb in ("hold", "remove", "withdraw"):
        run = passes.Pass(config, project, datetime.now(UTC))
        made = getattr(acts, args.verb)(args, run, _asks(config, project))
        if not (made.line.startswith(f"held {args.slug}; run ") and ", and " not in made.line):
            print(made.line)
    elif args.verb == "rename":
        at, by = config.user.stamp(queue.clock()), queue.who(queue.runner())
        print(queue.rename(state, args.slug, args.new, at, by, _asks(config, project)))
    elif args.verb == "move":
        _move(config, project, args.slug, args.to)
    try:
        table = queue.shown(queue.load(state), args.verb == "show" and args.all)
        if args.verb == "show":
            said = needs.lines(config, [project], project.name, verbs.clock())
            if said[0].startswith("waiting on "):
                print(*said, "", sep="\n")
        print(table, end="")
        if args.verb == "show":
            print(queue.noted(state, queue.load(state)), end="")
    except queue.Unparsable as error:
        print(f"refused: {error}")
        return 1
    return 0


def _went(
    config: jbus.Config, project: jbus.Project, slug: str, text: str, ref: str, said: list[str]
) -> None:
    """Log the go that `queue add --message` gave in its write, as `queue apply` logs the go of a
    batch (`acts.batch`), and mark what waited on it as acted on."""
    run = passes.Pass(config, project, datetime.now(UTC))
    done = f"approved {slug}:"
    line = next((one for one in said if one.startswith(done)), "")
    action = party.Action("go", slug, judgement.brief_sha(text)[:12])
    evidence = party.Evidence("t3-message", ref)
    with acts.locked(run.state, acts.LOCK):
        acts.logged(run, party.HOME, action, evidence, "done", line)
    waiting.acted(run, "go", slug)


def _move(config: jbus.Config, project: jbus.Project, slug: str, scope: str) -> None:
    """`jbus queue move`: give the row to the scope's home (`queue.move`), carry a fix's tries to
    that home's ledger (`blockers.rehome`), and log the move as one quiet `move` event. The carry
    runs on a move that moved nothing too, so a move cut short before it finishes when run again."""
    state, home = config.state(project), config.home(project)
    at, by = config.user.stamp(queue.clock()), queue.who(queue.runner())
    made = queue.move(state, home, slug, scope, at, by)
    print(made.line)
    blockers.rehome(home, slug, made.text)
    if not made.moved:
        return
    row = queue.fresh(state, slug)
    shown = queue.render([row]) if row else ""
    wake.Box(state, project).send(slug, "move", f"queue {project.name}: {made.line}", shown)


def _warn(config: jbus.Config, project: jbus.Project, slug: str, text: str) -> None:
    """Print what a brief that `add` queues, or that `check` passes, is warned of
    (`jbriefs.parse.warnings`), one `warning:` line each, and each door its commands walk through
    that no `Holds:` line names (`party.undeclared`), one `holds:` line each: the row holds for it
    all the same, and the line tells the home to write it. It warns as well of each `Where:` path
    the brief shares with a queued row its `Builds on:` line names (`briefs.shared_where`), and of
    an `Asked:` line that names no file of the home's `asked/` or a `Task:` quote that file does not
    hold (`_asked_warnings`)."""
    try:
        check = (config.home(project) / "fresh-check").read_text()
    except OSError:
        check = ""
    for warned in briefs.warnings(text, check):
        print(f"warning: {slug}'s {warned}")
    for warned in _asked_warnings(config.home(project), text):
        print(f"warning: {slug}'s {warned}")
    for case, command in party.undeclared(text):
        print(f"holds: {case}, from {command}")
    for other in sorted(chains.builds_on(judgement.body(text))):
        shared = briefs.shared_where(text, queue.brief(config.state(project), other) or "")
        if shared:
            print(
                f"warning: {slug} shares {', '.join(shared)} with {other}, which it builds on: "
                "join the rows where they are one change, take the shared path out of one where "
                f"{slug} has no need of {other}'s code, and leave it where it does"
            )


_QUOTE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')
_CUT = re.compile(r"\.\.\.|…|\[[^\]]*\]")
_WORDS = re.compile(r"\w+(?:'\w+)*")


def _words(text: str) -> str:
    """The text as its words, lowercased, one space between each, with a space at each end: a
    quote's words are the file's when this of the quote is in this of the file."""
    said = text.replace("’", "'").replace("‘", "'").lower()
    return f" {' '.join(_WORDS.findall(said))} "


def _asked_warnings(home: Path, text: str) -> list[str]:
    """What a brief's `Asked:` line is warned of: a path that is no file under the home's
    `asked/`, where the home keeps each request of the user's once, and each quote on `Task:`
    whose words that file does not hold, since a quote there holds only words the user typed.

    The path may start with `$H` or `~`, and a relative one is read from the home. A quote is
    one in straight or curly double quotes outside a code span, and a `...`, a `…` or a
    bracketed insert cuts it into parts, each checked alone. A brief with no `Asked:` line is
    warned of nothing here: it comes from no message of the user's."""
    said = brief_head.head(text, "Asked:")
    if not said:
        return []
    written = said.strip("`")
    path = Path(written.replace("$H", str(home), 1)).expanduser()
    path = (home / path).resolve()
    kept = (home / "asked").resolve()
    if not (path.is_relative_to(kept) and path.is_file()):
        return [
            f"brief's Asked: {written} is no file under the home's asked/: the home writes the "
            "user's request there once, as $H/asked/<entry>.md"
        ]
    held = _words(path.read_text(errors="replace"))
    task = " ".join(" ".join(lines) for label, lines in briefs.fields(text) if label == "Task")
    warned = []
    for quote in _QUOTE.finditer(re.sub(r"`[^`]*`", " ", task)):
        words = quote[1] or quote[2]
        parts = [_words(part) for part in _CUT.split(words)]
        if any(part.strip() and part not in held for part in parts):
            warned.append(
                f'brief\'s Task: quotes "{words}", which {written} does not hold: a quote holds '
                "only words the user typed"
            )
    return warned


def _check(config: jbus.Config, project: jbus.Project, given: str | None, home: str | None) -> int:
    """`jbus queue check`: print each fault for which `add` would refuse the brief on stdin, one
    a line, and what `add` would warn of, and write nothing. Exit 1 when there is a fault.

    The slug is the one given, or the first word of the brief's `# <slug>: <title>` line. The
    faults are `add`'s own (`queue.refusals`), with the brief's `Home:` line checked as `add`
    checks it, `--for` included. A fix's cap on retries is not checked, since counting the
    fix is a write (`blockers.admit`)."""
    text = verbs.piped("queue check", "the brief", "")
    first = next(iter(text.splitlines()), "")
    slug = given or first.removeprefix("# ").partition(":")[0].strip()
    try:
        fault = queue.owned(config.home(project), project.name, slug, text, None, home)
    except jbus.Refused as refused:
        fault = str(refused).removeprefix("refused: ").removesuffix(": nothing is queued")
    found = queue.refusals(config.state(project), slug, text, fault)
    for line in found:
        print(line)
    _warn(config, project, slug, text)
    return 1 if found else 0


def _item(state: Path, slug: str, given: str) -> str:
    """Pick the work item that a newly added row links to. The first choice is the item that
    `--item` names, which must be one the row can link to. Next is the item the row has, then
    the item a pass linked to its slug. Last, this function reserves a new item for the row
    now (`jbus.item`)."""
    if given:
        item.linkable(state, given, slug)
        return given
    try:
        row = next((row for row in queue.load(state) if row["slug"] == slug), None)
    except queue.Unparsable:
        row = None
    linked = item.by_slug(item.items(state)).get(slug)
    return (row or {}).get("item") or (linked.id if linked else "") or item.reserve(state)


def _verify(state: Path, slug: str, given: str | None) -> int:
    """Print, as JSON, the row's approval record and the brief that this verb checks against
    it: the stored brief, or the file `--brief` names. Exit 0 when the approval still applies
    to that brief."""
    try:
        row = next((row for row in queue.load(state) if row["slug"] == slug), None)
    except queue.Unparsable as error:
        print(f"refused: {error}")
        return 1
    if row is None:
        said = queue.was_removed(state, slug)
        print(f"refused: the queue has no row {slug}" + (f": {said}" if said else ""))
        return 1
    where = Path(given) if given else queue.brief_path(state, slug)
    try:
        text: str | None = where.read_text()
    except OSError:
        text = None
    found = queue.verify(row, text, str(where))
    print(json.dumps(found, indent=2))
    return 0 if found["holds"] else 1


def _table(table: argparse.ArgumentParser) -> None:
    table_verbs = table.add_subparsers(dest="verb", required=True)
    show = table_verbs.add_parser(
        "show", help="the rows still open, as Markdown", allow_abbrev=False
    )
    show.add_argument("--all", action="store_true", help="every row, the finished ones too")
    add = table_verbs.add_parser(
        "add",
        help="a row, with its brief on stdin",
        description=f"Queue a row, with its brief on stdin. A follow-up: {queue.FOLLOW_UP}.",
        allow_abbrev=False,
    )
    add.add_argument("slug")
    add.add_argument("--priority", type=int, required=True, help="an integer, lower first")
    add.add_argument(
        "--depends",
        help="slugs that must be merged before this row launches, with commas: each one the "
        "brief's Builds on: line names",
    )
    add.add_argument(
        "--merge-after",
        help="slugs whose pull requests merge before this row's, with commas: jmerge waits",
    )
    add.add_argument("--entry", help="the plan entry the row is work for, when not its own slug")
    add.add_argument("--item", help="the work item the row is, by its id; with none, one is made")
    add.add_argument(
        "--from",
        dest="adder",
        metavar="THREAD",
        help="the thread of the home that adds the row, empty for the uncategorized home: a brief "
        "whose Home: line names another home is refused, and the root home, which owns no row, "
        "gives --for",
    )
    add.add_argument(
        "--for",
        dest="handed",
        metavar="HOME",
        help="the scope the brief's Home: line resolves to, uncategorized where it names no scope: "
        "the row is that home's, handed over on purpose",
    )
    add.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="the user's own message in T3 Code that gives the go for this brief: the row is "
        "approved on it in the same write, as queue approve --message approves it",
    )
    approve = table_verbs.add_parser(
        "approve", help="record the go for the brief the user was shown", allow_abbrev=False
    )
    approve.add_argument("slug")
    approve.add_argument("--word", metavar="ID", help="a word `jbus word` kept, by its id")
    approve.add_argument("--answer", metavar="NUMBER", help="the answer that closed a question")
    approve.add_argument(
        "--message", metavar="THREAD/MESSAGE", help="the user's own message in T3 Code"
    )
    approve.add_argument(
        "--pick",
        metavar="THREAD/ITEM",
        help="the user's own answer to a question box in T3 Code, by its thread and its "
        "user_input_request item: it approves the row a picked label names",
    )
    approve.add_argument(
        "--rule",
        metavar="N",
        help="taken beside --follows and not read: the follow-up rule is known by what it says",
    )
    approve.add_argument(
        "--follows",
        metavar="SLUG",
        help="the approved row that this one follows up: its go is the ground",
    )
    approve.add_argument("--by", help=argparse.SUPPRESS)
    approve.add_argument("--at", help=argparse.SUPPRESS)
    approve.add_argument(
        "--sha",
        help="the first 12 of the sha256 of the brief the user was shown: needed with the "
        "user's word, and taken and not read beside --follows",
    )
    approve.add_argument(
        "--seen",
        metavar="EVENT",
        help="the id of the last event you read (jbus events): refused as stale when the row "
        "changed after it",
    )
    table_verbs.add_parser(
        "hold", help="take a row's approval back: no launch, and no merge"
    ).add_argument("slug")
    remove = table_verbs.add_parser(
        "remove", help="take a row out of the queue for good", allow_abbrev=False
    )
    remove.add_argument("slug")
    remove.add_argument(
        "--message", metavar="THREAD/MESSAGE", help="the user's own message in T3 Code"
    )
    remove.add_argument("--by", help="the user's name, with --at, for words that were typed")
    remove.add_argument("--at", help='"<YYYY-MM-DD HH:MM ZONE>", when the user said it')
    withdraw = table_verbs.add_parser(
        "withdraw",
        help="take out a row that never launched, as the home that runs it: for a row of "
        "your own that is not needed",
        allow_abbrev=False,
    )
    withdraw.add_argument("slug")
    withdraw.add_argument("--why", required=True, help="why the row is not needed, kept with it")
    rename = table_verbs.add_parser(
        "rename",
        help="move a row that never launched to a new slug, with its columns and its go",
        allow_abbrev=False,
    )
    rename.add_argument("slug")
    rename.add_argument("new", help="the new slug; the old one is retired")
    move = table_verbs.add_parser(
        "move",
        help="give a row to another child home, with its go: rewrites its brief's Home: line",
        allow_abbrev=False,
    )
    move.add_argument("slug")
    move.add_argument(
        "--home",
        dest="to",
        required=True,
        metavar="SCOPE",
        help="the scope whose home takes the row; never root",
    )
    table_verbs.add_parser("apply", help="a batch of the four verbs on stdin, all or none")
    verify = table_verbs.add_parser(
        "verify",
        help="the row's approval record and whether it holds for a brief, as JSON",
        allow_abbrev=False,
    )
    verify.add_argument("slug")
    verify.add_argument("--brief", metavar="PATH", help="the brief to check, not the stored one")
    check = table_verbs.add_parser(
        "check",
        help="the faults of the lines of the brief on stdin, one a line; writes nothing",
        description="Check the lines of the brief on stdin as add does, and write nothing: exit 0 "
        "when they have no fault, 1 with one fault a line. Warnings print as add prints them.",
        allow_abbrev=False,
    )
    check.add_argument("slug", nargs="?", help="the row's slug; by default the brief's # <slug>")
    check.add_argument(
        "--for",
        dest="handed",
        metavar="HOME",
        help="the scope the brief's Home: line resolves to, as add takes it",
    )


VERBS = (verbs.Verb("queue", "the queue table and the Chef's four verbs", _table, _queue),)
