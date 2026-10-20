"""Steering a work item, and the user's go for one by its id: the verbs of `jbus item`.

`steer` is the one place a steer is decided, from the chat, the view or the command: a
message to the item's home, a hold of its row's go, or a redirect to a new brief. It is one
`steered` line of the item's log (`jbus.item`), refused and writing nothing where the item
moved since the line its writer saw. `approve` is the user's go for an item by its id,
taken from chat only where the words name the item and its risk is routine.

A message is sent to the thread of the item's home through `word.post`, and what became of
it is kept in `item-sends.json` beside the log, since a send is no move: a pass sends each
one that has not gone (`deliver`). A redirect's line is written before its row changes, and
the first step of a pass finishes the row of one that died between the two (`settle`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbriefs import parse as briefs
from jbus import Refused, questions, queue, read_json, t3, verbs, wake, word, write_json
from jbus.item import (
    OWNER,
    SENDS,
    Item,
    Risk,
    Steer,
    Verb,
    Where,
    _current,
    _locked,
    _number,
    _put,
    by_slug,
    items,
    judged,
    listed,
    read,
    refusal,
    shown,
    told,
    write,
)

SENT = "item.sent"
TO_HOME = "jbus: a steer of {item}, {title}, said in the {where}, line {id}. {whose}\n\n{words}"
OWN = "It is {user}'s own word, as {basis} {ref} has it: take it as said by {user}."
AGENTS = (
    "It is a steer by {by}, not {user}'s word: weigh it as an agent's, and it approves nothing."
)
CONFIRM = "refused: a hold takes --confirm: it takes the row's go back, and nothing is written"
BASES = ("message", "word", "answer")


@dataclass(frozen=True)
class Basis:
    """The words of the user's a steer by him rests on, as an approval names them
    (`queue.basis`): a word `jbus word` kept, the answer that closed a question, or a message
    jbus read from T3 Code."""

    kind: str
    ref: str
    said: queue.Said


def steer(
    state: Path,
    box: wake.Box,
    id: str,
    action: Steer | str,
    words: str,
    seen: str,
    by: str,
    where: Where | str,
    confirm: bool,
    *,
    user: jsettings.Settings,
    basis: Basis | None = None,
    thread: str = "",
) -> dict[str, Any]:
    """The one place a steer is decided: a message to the item's home, a hold of its go, or a
    redirect to a new brief. The answer is the `steered` line it wrote.

    It is refused, and writes nothing, where the item's last line is not `seen` (the answer
    quotes the line that came after), so the same steer sent twice is written once. A steer
    by the user rests on a word of his (`basis`); any other is by the agent that ran it, as
    `by` and `thread` name it, with `ran_by` as an approval records it. A hold takes
    `confirm`, and takes the row's go back as `jbus queue hold` does. A redirect writes
    `words` as the row's brief and takes its go back in the same batch, so the item is
    proposed again, and only an approval by its id approves it (`Item.redirect`).

    A hold changes the row before the line, both under `items.lock`: a hold that dies
    between the two is made again by the same steer, whose `seen` still holds. A redirect
    writes its line first, with the new brief, and then the row: a redirect that dies between
    the two is marked already, so nothing approves the item, and the first pass finishes the
    row's change before it launches anything (`settle`). A message is sent after the line
    (`deliver`), and one T3 Code did not take is sent by the next pass.
    """
    action, where = Steer(action), Where(where)
    if where is Where.PASS:
        raise Refused("refused: a steer is said in the chat, the view or the command")
    if not by.strip():
        raise Refused("refused: a steer names who steers, with --by")
    if basis is None and user.user.casefold().startswith(by.strip().casefold()):
        raise Refused(
            f"refused: a steer by {user.user} rests on his word: --message, --word or --answer"
        )
    if basis is not None and by != user.user:
        raise Refused(f"refused: --{basis.kind} is {user.user}'s word, so --by is {user.user}")
    who = by if basis else by + (f", thread {thread}" if thread else "")
    said = words if action is Steer.REDIRECT else " ".join(words.split())
    if action is Steer.MESSAGE and not said:
        raise Refused("refused: a message steer has words")
    if action is Steer.HOLD and not confirm:
        raise Refused(CONFIRM)
    if action is Steer.REDIRECT and not said.strip():
        raise Refused("refused: a redirect has the new brief on stdin")
    more: dict[str, Any] = {"action": str(action), "ran_by": queue.runner()}
    if basis is not None:
        heard = basis.said
        more.update(
            basis=basis.kind,
            ref=basis.ref,
            said=heard.words,
            said_at=heard.said_at,
            said_in=heard.said_in,
            checked=heard.checked,
        )
    with _locked(state):
        item = _current(read(state), id, action, seen)
        if action is Steer.MESSAGE:
            line, more["words"] = f"message by {who}: {said}", said
        elif action is Steer.HOLD:
            held = queue.hold(state, item.slug) if item.slug else f"held {id}, which has no row"
            line = f"hold by {who}: {held}" + (f": {said}" if said else "")
            if said:
                more["words"] = said
        else:
            _redirectable(state, item, said)
            line = f"redirect by {who}: {item.slug}'s brief is {queue.brief_sha(said)[:12]} now"
            more.update(brief=said, brief_sha=queue.brief_sha(said))
        made = _put(state, Verb.STEER, item=id, by=who, where=where, line=line, seen=seen, **more)
        if action is Steer.REDIRECT:
            made = {**made, "line": f"{line}; {_redirect(state, made)}"}
    told(box, made)
    return made


def _redirectable(state: Path, item: Item, text: str) -> None:
    """Refuse a redirect the queue would refuse, before its line is written: an item with no
    row, and a brief a launch would refuse (`jbriefs.parse.faults`)."""
    if not item.slug:
        raise Refused(f"refused: {item.id} has no row, so it has no brief to redirect")
    if queue.fresh(state, item.slug) is None:
        raise Refused(f"refused: the queue has no row {item.slug}")
    faults = briefs.faults(queue.body(text))
    if faults:
        lines = "".join(f"\n- {fault}" for fault in faults)
        raise Refused(
            f"refused: the new brief of {item.slug} has faults, and nothing is written{lines}"
        )


def _redirect(state: Path, made: dict[str, Any]) -> str:
    """Write a redirect line's brief as the brief of the item's row and take its go back, in
    one batch of the queue: `Add` alone keeps a go whose brief means the same, and a redirect
    is never approved by the go it had. The answer says what the queue did, or nothing where
    the row has the brief and no go already, so a second run is the first."""
    slug = items(state)[made["item"]].slug
    row = queue.fresh(state, slug)
    if row is None:
        return ""
    stored = queue.brief(state, slug) or ""
    if not row.get("approved") and queue.brief_sha(stored) == made["brief_sha"]:
        return ""
    add = queue.Add(
        slug,
        row.get("priority", 0),
        row.get("depends", []),
        made["brief"],
        row.get("entry", ""),
        row.get("item", ""),
        row.get("merge_after", []),
    )
    added, held = queue._run(state, [(0, add), (0, queue.Hold(slug))])
    return f"{added}; {held}, and it waits for an approval by its id"


def settle(state: Path) -> list[str]:
    """Finish the row's change of each redirect not yet approved by its id: one whose steer
    died after its line was written. The answer is what the queue did, one line each."""
    lines = {one.get("id"): one for one in read(state)}
    done = []
    for item in items(state).values():
        made = lines.get(item.redirect)
        if made and made.get("brief") and item.slug:
            try:
                said = _redirect(state, made)
            except Refused:
                continue
            if said:
                done.append(f"item {item.id}: redirect {item.redirect} finished, {said}")
    return done


def approvable(state: Path, slug: str) -> None:
    """Refuse an approval of a row, by any basis, whose item was redirected and has not been
    approved by its id since: a redirected item is never approved by the row's go."""
    item = by_slug(items(state)).get(slug)
    if item is not None and item.redirect:
        raise Refused(
            f"refused: {slug} is {item.id}, which was redirected at {item.redirect}: no "
            f"approval of the row gives it a go until {item.id} is approved by its id, "
            f"jbus item approve {item.id} in the view or the command"
        )


def names(words: str, item: Item) -> bool:
    """Whether the words name the item: its id or its slug, as a whole name."""
    return any(
        name and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", words, re.I)
        for name in (item.id, item.slug)
    )


def approve(
    state: Path,
    box: wake.Box,
    id: str,
    *,
    by: str,
    where: Where | str,
    words: str,
    seen: str | None,
    user: jsettings.Settings,
    project: str,
) -> dict[str, Any]:
    """The user's go for an item, by its id. The answer is the `approved` line.

    From chat it is taken only where the words name the item and its risk is `routine`: a
    review item is approved in the view, whose link the refusal names, and so is one that
    was redirected. Its line has `by_id`, which ends a redirect (`Item.redirect`). Before
    it ends one, it finishes the redirect's row change where a steer died before making it
    (`_redirect`), under the same lock: once the mark is gone, `settle` no longer looks.
    """
    where = Where(where)
    if by != user.user:
        raise Refused(f"refused: only {user.user} approves an item, not {by}")
    said = f"approve by {by}" + (f": {words}" if words else "")
    more: dict[str, Any] = {"by_id": True, **({"words": words} if words else {})}
    with _locked(state):
        if where is Where.CHAT:
            _from_chat(state, id, words, project)
        _finish(state, id)
        made = _put(state, Verb.APPROVE, item=id, by=by, where=where, line=said, seen=seen, **more)
    told(box, made)
    return made


def _finish(state: Path, id: str) -> None:
    """Make the row change of the item's open redirect, where its line is written and the
    row has not changed: nothing where there is no redirect, or the row has it already."""
    item = items(state).get(id)
    if item is None or not item.redirect:
        return
    made = next((one for one in read(state) if one.get("id") == item.redirect), None)
    if made and made.get("brief") and item.slug:
        _redirect(state, made)


def _from_chat(state: Path, id: str, words: str, project: str) -> None:
    """Refuse an approval from chat whose words do not name the item, of a review item, or
    of a redirected one. It is asked with `items.lock` held, so no line comes between."""
    item = items(state).get(id)
    if item is None:
        raise Refused(refusal(None, Verb.APPROVE, id))
    link = f"#/{project}/item/{id}"
    if not names(words, item):
        slug = f" or its slug {item.slug}" if item.slug else ""
        raise Refused(
            f"refused: an approval from chat names the item, {id}{slug}, and these words "
            f"name neither: approve it in the view, {link}"
        )
    if judged(state, item).risk is Risk.REVIEW:
        raise Refused(
            f"refused: {id} is a review item, approved in the view and not from chat: {link}"
        )
    if item.redirect:
        raise Refused(
            f"refused: {id} was redirected at {item.redirect}, and a redirected item is "
            f"approved in the view or the command, not from chat: {link}"
        )


def sends(state: Path) -> dict[str, dict[str, str]]:
    """What became of each message steer, by its line's id: the thread it went to, when, and
    why it waits where it has not gone. The log is only appended to, and a send is no move,
    so it is kept beside it, in `item-sends.json`."""
    kept = read_json(state / SENDS, {})
    return kept if isinstance(kept, dict) else {}


def deliver(
    state: Path,
    box: wake.Box,
    home: Path,
    client: t3.Client | None,
    user: str,
    now: datetime,
) -> dict[str, dict[str, str]]:
    """Send each message steer that has not gone to the thread of the item's home, as one
    queued message under the retry key `item|<project>|<id>|<line id>`, through `word.post`:
    the command and a pass may both send one, and T3 Code takes it once. The answer is what
    became of each it tried, by line id. Why one waits is written once, and again when the
    reason changes, each time with a quiet event."""
    project, found, tried = box.project.name, None, {}
    for line in read(state):
        if line.get("verb") != Verb.STEER or line.get("action") != Steer.MESSAGE:
            continue
        was = sends(state).get(line["id"], {})
        if was.get("sent_at"):
            continue
        found = found or items(state)
        item = found.get(line["item"])
        title = item.title if item else ""
        whose = OWN if line.get("basis") else AGENTS
        message = TO_HOME.format(
            title=title or "(no title)",
            whose=whose.format(user=user, **line),
            **{**line, "words": line.get("words", "")},
        )
        thread = word.home(home)
        key = f"item|{project}|{line['item']}|{line['id']}"
        waits = word.post(client, thread, message, key)
        at = "" if waits else now.astimezone(UTC).isoformat(timespec="seconds")
        now_is = {"thread": thread if not waits else "", "sent_at": at, "waits": waits}
        tried[line["id"]] = now_is
        if waits and waits == was.get("waits"):
            continue
        with _locked(state):
            kept = sends(state)
            if kept.get(line["id"], {}).get("sent_at"):
                continue
            write_json(state / SENDS, {**kept, line["id"]: now_is}, mode=0o600)
        how = f"sent to {thread}" if at else f"waits, {waits}"
        said = f"item {project}: {line['item']} message {line['id']} {how}"
        box.record(SENT, said, line.get("words", ""), item=line["item"], item_line=line["id"])
    return tried


def _arguments(parser: argparse.ArgumentParser) -> None:
    item_verbs = parser.add_subparsers(dest="verb", required=True)
    where = [str(one) for one in Where if one is not Where.PASS]
    propose = item_verbs.add_parser("propose", help="a new item, with no row", allow_abbrev=False)
    propose.add_argument("--title", required=True)
    propose.add_argument("--by", required=True, help="who proposes it")
    propose.add_argument("--where", choices=where, default="cli", help="where it was said")
    propose.add_argument("--owner", default=OWNER, help="who will do it")
    for name, help in (
        ("approve", "the user's go for an item"),
        ("drop", "an item that will not be done"),
    ):
        one = item_verbs.add_parser(name, help=help, allow_abbrev=False)
        one.add_argument("id")
        one.add_argument("--by", required=True)
        one.add_argument("--where", choices=where, default="cli")
        one.add_argument("--words", default="", help="what was said, as it was said")
        one.add_argument("--seen", help="the last line of the item its writer saw")
    steer = item_verbs.add_parser(
        "steer",
        help="message the item's home, hold its go, or redirect it to a new brief on stdin",
        allow_abbrev=False,
    )
    steer.add_argument("id")
    steer.add_argument("action", choices=[str(one) for one in Steer])
    steer.add_argument("--seen", required=True, help="the item's last line, as the steerer saw it")
    steer.add_argument("--by", required=True, help="the agent's role, or the user with a basis")
    steer.add_argument("--where", choices=where, default="cli", help="where it was said")
    steer.add_argument("--from", dest="thread", default="", help="the thread steering it")
    steer.add_argument("--confirm", action="store_true", help="a hold takes it")
    bases = steer.add_mutually_exclusive_group()
    bases.add_argument(
        "--message", metavar="THREAD/MESSAGE", help="the user's own message in T3 Code"
    )
    bases.add_argument("--word", metavar="ID", help="a word `jbus word` kept, by its id")
    bases.add_argument("--answer", metavar="NUMBER", help="the answer that closed a question")
    steer.add_argument("words", nargs="*", help="the message, or why it is held")
    show = item_verbs.add_parser("show", help="an item, its risk and its lines", allow_abbrev=False)
    show.add_argument("id")
    item_verbs.add_parser("list", help="every item, one line each", allow_abbrev=False)


def _item(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state = config.state(project)
    box = wake.Box(state, project)
    if args.verb == "propose":
        made = write(
            state,
            box,
            Verb.PROPOSE,
            by=args.by,
            where=Where(args.where),
            line=f"proposed by {args.by}",
            project=project.name,
            title=args.title,
            owner=args.owner,
        )
        print(f"proposed {made['item']}: {args.title}")
        return 0
    if args.verb == "approve":
        approve(
            state,
            box,
            args.id,
            by=args.by,
            where=args.where,
            words=args.words,
            seen=args.seen,
            user=config.user,
            project=project.name,
        )
        print(f"approved {args.id}")
        return 0
    if args.verb == "drop":
        said = f"drop by {args.by}" + (f": {args.words}" if args.words else "")
        more = {"words": args.words} if args.words else {}
        where = Where(args.where)
        write(
            state,
            box,
            Verb.DROP,
            item=args.id,
            by=args.by,
            where=where,
            line=said,
            seen=args.seen,
            **more,
        )
        print(f"dropped {args.id}")
        return 0
    if args.verb == "steer":
        return _steer(args, config, project, state, box)
    found = items(state)
    if args.verb == "show":
        if args.id not in found:
            raise Refused(f"refused: there is no item {args.id}")
        print(shown(state, found[args.id]), end="")
        return 0
    for one in sorted(found.values(), key=lambda one: _number(one.id)):
        print(listed(judged(state, one)))
    return 0


def _basis(args: argparse.Namespace, config: jbus.Config, state: Path) -> Basis | None:
    """The word of the user's a steer names, read where it is kept, or None for none."""
    for kind in BASES:
        ref = getattr(args, kind)
        if ref:
            if kind == "message":
                return Basis(kind, ref, t3.heard(config, ref))
            reads = word.basis if kind == "word" else questions.basis
            return Basis(kind, ref, reads(state, ref))
    return None


def _steer(
    args: argparse.Namespace,
    config: jbus.Config,
    project: jbus.Project,
    state: Path,
    box: wake.Box,
) -> int:
    """`jbus item steer`: the steer, and for a message, whether it went."""
    words = sys.stdin.read() if args.action == Steer.REDIRECT else " ".join(args.words)
    made = steer(
        state,
        box,
        args.id,
        args.action,
        words,
        args.seen,
        args.by,
        args.where,
        args.confirm,
        user=config.user,
        basis=_basis(args, config, state),
        thread=args.thread,
    )
    said = f"steered {args.id}: {made['id']} {args.action}, {made['line']}"
    if args.action != Steer.MESSAGE:
        print(said)
        return 0
    try:
        client: t3.Client | None = t3.Client(config.server, config.token_path)
    except Refused:
        client = None
    now = datetime.now(UTC)
    went = deliver(state, box, config.home(project), client, config.user.user, now)
    one = went.get(made["id"]) or sends(state).get(made["id"], {})
    if one.get("sent_at"):
        print(f"{said}; sent to {one['thread']}")
    else:
        print(f"{said}; recorded and not sent, {one.get('waits', '')}: the next pass sends it")
    return 0


def _deliver(half: Any) -> None:
    """`deliver` as a step of the pass: each message steer T3 Code has not taken yet."""
    run = half.run
    went = deliver(run.state, run.box, run.home, half.client, run.user.user, run.now)
    for name, one in went.items():
        if one["sent_at"]:
            run.say(f"item {run.project.name}: message {name} sent to {one['thread']}")


def _settle(half: Any) -> None:
    """`settle` as a step of the pass, first in it, so a launch finds every redirect's row."""
    for said in settle(half.run.state):
        half.run.say(said)


STEPS = (
    verbs.Step("before-watch", 7, "item.settle", _settle),
    verbs.Step("before-watch", 15, "item.deliver", _deliver, ("client",)),
)
VERBS = (
    verbs.Verb("item", "work items: propose, approve, steer, drop, show, list", _arguments, _item),
)
