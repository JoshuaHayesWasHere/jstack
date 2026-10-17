"""`jbus queue`: the verbs on the queue's table, and what they ask of everything else.

The table and its verbs are `jbus.queue`, which asks nobody: what a removal or an approval
needs to know of T3 Code, GitHub, the launches and the words that were kept, it is given as
a `queue.Asks`. `_asks` makes that one for a project, out of the modules that know, each of
which is built on the queue. So the verb is declared here, above them all, and not in
`jbus.queue`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
from jbus import dispatch, item, lavish, questions, queue, t3, verbs, waiting, wake, watch, word


def _asks(config: jbus.Config, project: jbus.Project) -> queue.Asks:
    """What `queue remove` and `queue approve` ask, and the one quiet event a removal sends.

    `said` gives the words an approval names: a word of the project's `words.json`, the
    answer of a closed question of its `questions.json`, a message read from T3 Code, a pick
    read from Lavish's state file, or a rule of the home's `standing.md`.

    `out` asks T3 Code and GitHub now: a thread that is at work, an open pull request, or a
    merged one. A thread that ended or was settled is not out. Where either cannot be asked,
    that is said, and nothing is known. `launched` reads the launch records: one at
    `intent` is a launch T3 Code has not answered yet, and one written since this began is a
    pass that launched the slug after `out` was asked. The event has the row as it was,
    waits in the outbox, and starts no POST.
    """
    run = wake.Pass(config, project, datetime.now(UTC))
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

    def out(slug: str) -> str:
        try:
            client = t3.Client(config.server, config.token_path)
            listed = watch.crew_threads(client, project.project_id, f"{watch.TITLE}{slug}")
        except (jbus.Refused, t3.T3Error) as error:
            why = str(error).removeprefix("refused: ")
            asked = f"T3 Code could not be asked whether {slug}'s thread is out"
            raise jbus.Refused(f"refused: {asked} ({why})") from error
        for thread in listed:
            mine = thread["title"].removeprefix(watch.TITLE).strip() == slug
            if mine and not thread.get("settled") and thread["status"] in watch.LIVE:
                return f"{slug} is out: its thread {thread['threadId']} is {thread['status']}"
        for state, said in (
            ("open", "{slug} is out: its pull request #{number} is open"),
            ("merged", "{slug} merged as #{number}, and a merged row stays"),
        ):
            found = watch.pulls(run, state, "number", "--head", slug, "--limit", "1")
            if found is None:
                asked = f"GitHub could not be asked whether {slug} has a pull request"
                raise jbus.Refused(f"refused: {asked}")
            if found:
                return said.format(slug=slug, number=found[0]["number"])
        return ""

    def said(basis: str, ref: str) -> queue.Said:
        if basis == "message":
            return t3.heard(config, ref)
        if basis == queue.PAGE:
            return lavish.picked(config.user, ref)
        if basis == queue.RULE:
            return queue.rule(config.home(project) / "standing.md", ref)
        return (word.basis if basis == "word" else questions.basis)(run.state, ref)

    return queue.Asks(out, launched, told, said)


def _queue(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state = config.state(project)
    if args.verb == "apply":
        asks = _asks(config, project)
        print("\n".join(queue.apply(state, sys.stdin.read(), config.user, asks)))
        return 0
    if args.verb == "verify":
        return _verify(state, args.slug, args.brief)
    if args.verb == "add":
        depends = queue.slugs(args.depends or "")
        text = sys.stdin.read()
        named = _item(state, args.slug, args.item or "")
        said = queue.add(state, args.slug, args.priority, depends, text, args.entry or "", named)
        if said.endswith((queue.GO_HOLDS, queue.GO_VOID)):
            print(said)
        row = queue.fresh(state, args.slug)
        if row is not None:
            by = queue.who(queue.runner())
            box = wake.Box(state, project)
            item.link(state, box, row, args.item or "", by, config.user.user)
    elif args.verb == "approve":
        rests = queue.basis(vars(args))
        queue.approve(state, args.slug, rests, args.sha, config.user, _asks(config, project))
    elif args.verb == "hold":
        held = queue.hold(state, args.slug)
        if held != f"held {args.slug}":
            print(held)
    elif args.verb == "remove":
        asks = _asks(config, project)
        print(queue.remove(state, args.slug, args.by, args.at, config.user, asks))
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
    """The work item a row that is added is linked to: the one `--item` names, which must be
    one it can be linked to, the one the row has, the one a pass linked to its slug, or one
    reserved for it now (`jbus.item`)."""
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
    """Print, as JSON, the row's approval record and the brief checked against it: the
    stored brief, or the file `--brief` names. It exits 0 when the go holds for that brief."""
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
    add = table_verbs.add_parser("add", help="a row, with its brief on stdin", allow_abbrev=False)
    add.add_argument("slug")
    add.add_argument("--priority", type=int, required=True, help="an integer, lower first")
    add.add_argument("--depends", help="slugs that must be merged first, with commas")
    add.add_argument("--entry", help="the plan entry the row is work for, when not its own slug")
    add.add_argument("--item", help="the work item the row is, by its id; with none, one is made")
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
        "--page", metavar="SESSION/ENTRY", help="the user's own send from a Lavish page"
    )
    approve.add_argument(
        "--rule", metavar="N", help="a rule of the home's standing.md, with --follows"
    )
    approve.add_argument(
        "--follows", metavar="SLUG", help="the row he approved that this one follows up"
    )
    approve.add_argument("--by", help=argparse.SUPPRESS)
    approve.add_argument("--at", help=argparse.SUPPRESS)
    approve.add_argument("--sha", required=True, help="the first 12 of that brief's sha256")
    table_verbs.add_parser("hold", help="take a row's approval back").add_argument("slug")
    remove = table_verbs.add_parser(
        "remove", help="take a row out of the queue for good", allow_abbrev=False
    )
    remove.add_argument("slug")
    remove.add_argument("--by", required=True)
    remove.add_argument("--at", required=True, help="as approve takes it")
    table_verbs.add_parser("apply", help="a batch of the four verbs on stdin, all or none")
    verify = table_verbs.add_parser(
        "verify",
        help="the row's approval record and whether it holds for a brief, as JSON",
        allow_abbrev=False,
    )
    verify.add_argument("slug")
    verify.add_argument("--brief", metavar="PATH", help="the brief to check, not the stored one")


VERBS = (verbs.Verb("queue", "the queue table and the Chef's four verbs", _table, _queue),)
