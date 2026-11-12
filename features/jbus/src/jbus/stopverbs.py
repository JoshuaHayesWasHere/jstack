"""`jbus stop`, the verb of `jbus.stop`: a scoped home's stop to the root, of any kind, and the
root's answer to one or its pass of one to the user, and the step of a pass that closes the stops
whose rows or entries ended and sends what waits."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jbus import Config, Refused, verbs
from jbus.passes import Pass
from jbus.stop import (
    DOOR,
    EVERY,
    KINDS,
    Unparsable,
    answer,
    deliver,
    load,
    passed,
    path,
    reread,
    settle,
    take,
    tell,
)
from jbus.t3 import Client

if TYPE_CHECKING:
    from jbus.poll import Half


def _client(config: Config) -> Client | None:
    try:
        return Client(config.server, config.token_path)
    except Refused:
        return None


def _tells(args: argparse.Namespace, config: Config) -> int:
    """`jbus tell`: keep the root's own message for one scope or every scope (`tell`), send it at
    once, and print one line for each scope. A pass sends what could not go."""
    run = Pass(config, verbs.project(config, args.project), datetime.now(UTC), lambda _: None)
    try:
        told = tell(run, args.thread, args.to, " ".join(args.words))
    except Refused as error:
        print(error)
        return 1
    deliver(run, _client(config))
    for one, new in told:
        if not new:
            print(f"held: {one.scope}, it already has this message from the root")
            continue
        now = reread(run.state, one)
        to = now.thread if now.sent_at else f"nobody yet, {now.waits}"
        print(f"told: {one.scope}, sent to {to}")
    return 0


def _tell_arguments(tell: argparse.ArgumentParser) -> None:
    tell.add_argument("to", metavar="SCOPE", help=f"the scoped home it goes to, or {EVERY}")
    tell.add_argument(
        "--from",
        dest="thread",
        metavar="THREAD",
        required=True,
        help="the root home's thread",
    )
    tell.add_argument("words", nargs="*", help="the root's own words")


def _reply(args: argparse.Namespace, run: Pass, config: Config) -> int:
    """`jbus stop answer` and `jbus stop pass`: the root's answer to a scope's stops on a row or an
    entry, or its pass of them to the user."""
    verb = args.row
    given = (args.on, args.outside, args.holds, args.entry, args.kind)
    if any(one is not None for one in given) or len(args.words) < 2 + (verb == "answer"):
        raise Refused(
            'refused: an answer is jbus stop answer <scope> <row or entry> "<text>" --from <root '
            'id>, and a pass is jbus stop pass <scope> <row or entry> ["<recommendation>"] --from '
            "<root id>"
        )
    scope, row, *words = args.words
    settle(run)
    if verb == "answer":
        made = answer(run, args.thread, scope, row, " ".join(words))
    else:
        made = passed(run, args.thread, scope, row, " ".join(words))
    deliver(run, _client(config))
    now = reread(run.state, made)
    to = now.thread if now.sent_at else f"nobody yet, {now.waits}"
    if verb == "answer":
        print(f"answered: {', '.join(made.stops)}, closed, the answer sent to {to}")
        return 0
    numbers = [one.question for one in load(run.state).stops if one.key in made.stops]
    gates = " and ".join(f"question {number}" for number in dict.fromkeys(numbers))
    told = f"is told at {to}" if now.sent_at else f"is told by {to}"
    print(
        f"passed: {', '.join(made.stops)}, closed, {gates} holds for the user, and the {scope} "
        f"home {told}"
    )
    return 0


def _stop(args: argparse.Namespace, config: Config) -> int:
    """`jbus stop`: a scoped home's stop to the root, or the root's answer to one or pass of one
    to the user (`take`, `answer`, `passed`). The command sends what it kept at once, and a pass
    sends what could not go."""
    run = Pass(config, verbs.project(config, args.project), datetime.now(UTC), lambda _: None)
    try:
        if args.row in ("answer", "pass"):
            return _reply(args, run, config)
        kind, entry = args.kind or DOOR, args.entry or ""
        words = [args.row, *args.words] if entry and args.row else args.words
        if not entry and not args.row:
            raise Refused("refused: a stop is on this home's own row, or on --entry <entry>")
        one = take(
            run,
            args.thread,
            "" if entry else args.row,
            args.on or "",
            args.outside or "",
            " ".join(words),
            args.holds or "",
            kind,
            entry,
        )
        settle(run)
        deliver(run, _client(config))
        now = reread(run.state, one)
        to = f"the root home at {now.thread}" if now.sent_at else f"nobody yet, {now.waits}"
        print(f"stopped: {one.key}, sent to {to}")
        return 0
    except Refused as error:
        print(error)
        return 1


def _arguments(stop: argparse.ArgumentParser) -> None:
    stop.add_argument(
        "row",
        nargs="?",
        help="this home's own open row; `answer` or `pass` for the root's reply; with --entry, "
        "the first word of what the root must clear",
    )
    stop.add_argument(
        "--kind",
        choices=KINDS,
        help="door (the default): a one-way door, with --holds and --on or --outside; decision "
        "or go: a choice or a go this home may not make alone, on its row or --entry",
    )
    stop.add_argument(
        "--entry", metavar="ENTRY", help="with --kind decision or go: an entry of this home's plan"
    )
    held = stop.add_mutually_exclusive_group()
    held.add_argument(
        "--on", metavar="ROW", help="the other home's open row, or #<n>, that holds it"
    )
    held.add_argument("--outside", metavar="WHAT", help="what holds it that no home owns")
    stop.add_argument(
        "--holds",
        metavar="CASE",
        help="the one-way door, a case of features/home/templates/gates.md, word for word",
    )
    stop.add_argument(
        "--from",
        dest="thread",
        metavar="THREAD",
        required=True,
        help="this home's thread: a scoped home's for a stop, the root's for an answer or a pass",
    )
    stop.add_argument(
        "words",
        nargs="*",
        help="what the root must clear; for an answer or a pass, <scope> <row or entry> and the "
        "root's words",
    )


VERBS = (
    verbs.Verb(
        "stop",
        "a scoped home's stop to the root, at a door or with a decision or a go, or the root's "
        "answer or its pass to the user",
        _arguments,
        _stop,
    ),
    verbs.Verb(
        "tell",
        "the root home's own message to one scoped home, or to every one, signed as the root's",
        _tell_arguments,
        _tells,
    ),
)


def _pass(half: Half) -> None:
    """Close the stops whose rows or entries ended, then carry the user's answers to passed
    stops and send what waits. A `stops.json` that does not parse
    raises a gate, and the pass goes on."""
    try:
        settle(half.run)
        deliver(half.run, half.client)
    except Unparsable:
        half.run.gate(half.run.project.name, "stops.json does not parse", str(path(half.run.state)))


STEPS = (verbs.Step("before-watch", 12, "stop.deliver", _pass),)
