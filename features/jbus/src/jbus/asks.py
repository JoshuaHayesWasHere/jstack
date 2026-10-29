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
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
from jbriefs import parse as briefs
from jbus import (
    acts,
    blockers,
    boxes,
    dispatch,
    item,
    lavish,
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
from jmerge.asked import Silent


def _asks(config: jbus.Config, project: jbus.Project) -> queue.Asks:
    """Return what `queue remove` and `queue approve` ask, and the one quiet event a removal
    sends.

    `said` returns the words an approval names: a word of the project's `acts.jsonl`, the
    answer of a closed question of its `questions.json`, a message read from T3 Code, the
    user's answer to a question box read from T3 Code and its store, a pick read from Lavish's
    state file. A follow-up's go reads no file of the home: jbus knows the rule by what it says.
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
        if basis == queue.PAGE:
            return lavish.picked(config.user, ref)
        return (word.basis if basis == "word" else questions.basis)(run.state, ref)

    goes = plan.entry_go(run.state, config.home(project))
    return queue.Asks(out, launched, told, said, goes)


def _queue(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
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
        return 0
    if args.verb == "verify":
        return _verify(state, args.slug, args.brief)
    if args.verb == "add":
        depends = queue.slugs(args.depends or "")
        text = verbs.piped("queue add", "the brief")
        queue.owned(config.home(project), project.name, args.slug, text, args.adder, args.handed)
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
            )
        except BaseException:
            release()
            raise
        if said.endswith((queue.GO_HOLDS, queue.GO_VOID)):
            print(said)
        for line in ruled:
            print(line)
        try:
            check = (config.home(project) / "fresh-check").read_text()
        except OSError:
            check = ""
        warned = briefs.check_asked(text, check)
        if warned:
            print(f"warning: {args.slug}'s {warned}")
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
        if made.line != f"held {args.slug}":
            print(made.line)
    elif args.verb == "rename":
        at, by = config.user.stamp(queue.clock()), queue.who(queue.runner())
        print(queue.rename(state, args.slug, args.new, at, by, _asks(config, project)))
    try:
        table = queue.shown(queue.load(state), args.verb == "show" and args.all)
        listed = waiting.read(state) or [] if args.verb == "show" else []
        if listed:
            print(f"waiting on {config.user.user}:", *(one["line"] for one in listed), "", sep="\n")
        print(table, end="")
        if args.verb == "show":
            print(queue.noted(state, queue.load(state)), end="")
    except queue.Unparsable as error:
        print(f"refused: {error}")
        return 1
    return 0


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
        help="the thread of the home that adds the row, empty for the root home: a brief whose "
        "Home: line names another home is refused",
    )
    add.add_argument(
        "--for",
        dest="handed",
        metavar="HOME",
        help="root, or the scope the brief's Home: line names: the row is that home's, "
        "handed over on purpose",
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
        "--page", metavar="SESSION/ENTRY", help="the user's own send from a Lavish page"
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
    remove.add_argument(
        "--page", metavar="SESSION/ENTRY", help="the user's own send from a Lavish page"
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
    table_verbs.add_parser("apply", help="a batch of the four verbs on stdin, all or none")
    verify = table_verbs.add_parser(
        "verify",
        help="the row's approval record and whether it holds for a brief, as JSON",
        allow_abbrev=False,
    )
    verify.add_argument("slug")
    verify.add_argument("--brief", metavar="PATH", help="the brief to check, not the stored one")


VERBS = (verbs.Verb("queue", "the queue table and the Chef's four verbs", _table, _queue),)
