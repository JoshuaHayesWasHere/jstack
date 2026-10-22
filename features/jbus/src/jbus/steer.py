"""This module steers a work item and records the user's go for one by its id: the verbs of
`jbus item`.

`steer` is the one place that decides a steer, whether it comes from the chat, the view or the
command. A steer is a message to the item's home, a hold of its row's go, or a redirect to a
new brief. It writes one `steered` line to the item's log (`jbus.item`). When the item has
moved since the line the steer's writer saw, `steer` refuses and writes nothing. `approve`
records the user's go for an item by its id. It takes a go from chat only when the words name
the item and the item's risk is routine.

`word.post` sends a message to the thread of the item's home. A send is no move, so what became
of the message is kept in `item-sends.json` beside the log, and a pass sends each message that
has not gone (`deliver`). `steer` writes a redirect's line before it changes the row. When a
redirect dies between the two, the first step of a pass finishes its row (`settle`).
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
from jbriefs.home import thread_of
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
CHAT = "chat"


@dataclass(frozen=True)
class Basis:
    """The user's words that a steer by the user rests on, named as an approval names them
    (`queue.basis`). They are a word `jbus word` kept, the answer that closed a question, or a
    message jbus read from T3 Code."""

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
    """Decide a steer, in the one place that does: a message to the item's home, a hold of
    its go, or a redirect to a new brief. Return the `steered` line it wrote.

    `steer` refuses and writes nothing when the item's last line is not `seen`, and the
    refusal quotes the line that came after. So the same steer sent twice is written once. A
    steer by the user rests on a word of the user's (`basis`). Any other steer is by the
    agent that ran it, as `by` and `thread` name it, with `ran_by` as an approval records it.
    A hold needs `confirm`, and takes the row's go back as `jbus queue hold` does. A redirect
    writes `words` as the row's brief and takes the row's go back in the same batch. So the
    item is proposed again, and only an approval by its id approves it (`Item.redirect`).

    A hold changes the row before it writes the line, both under `items.lock`. When a hold
    dies between the two, the same steer makes it again, since its `seen` still holds. A
    redirect writes its line first, with the new brief, and then the row. When a redirect
    dies between the two, the item already carries the mark, so nothing approves it, and the
    first pass finishes the row's change before it launches anything (`settle`). `deliver`
    sends a message after the line is written, and the next pass sends a message that T3
    Code did not take.
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
    more: dict[str, Any] = {"action": str(action), "ran_by": queue.runner(), **rests(basis)}
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


def rests(basis: Basis | None) -> dict[str, Any]:
    """Return what a line keeps of the user's word that it rests on, or nothing when there is
    none."""
    if basis is None:
        return {}
    heard = basis.said
    return {
        "basis": basis.kind,
        "ref": basis.ref,
        "said": heard.words,
        "said_at": heard.said_at,
        "said_in": heard.said_in,
        "checked": heard.checked,
    }


def chat(message: str, words: str, user: jsettings.Settings, now: datetime) -> Basis:
    """Return the user's words as Sous Chef's chat quotes them, by the chat message's id or
    link. Nothing reads them back from the chat, so the basis keeps them with
    `checked: false`."""
    said = queue.Said(" ".join(words.split()), user.stamp(now), "chat", False, message)
    return Basis(CHAT, message, said)


def _redirectable(state: Path, item: Item, text: str) -> None:
    """Refuse, before the line is written, a redirect that the queue would refuse: one for an
    item with no row, or one whose brief a launch would refuse (`jbriefs.parse.faults`)."""
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
    """Write a redirect line's brief as the brief of the item's row, and take the row's go
    back, in one batch of the queue. `Add` alone keeps a go when the brief means the same, and
    the go a row had never approves its redirect. Return what the queue did, or nothing when
    the row already has the brief and no go, so a second run does the same as the first."""
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
    """Finish the row's change of each redirect that is not yet approved by its id, which is a
    redirect whose steer died after it wrote its line. Return what the queue did, one line for
    each redirect."""
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
    """Refuse an approval of a row, by any basis, when the row's item was redirected and has
    not been approved by its id since. The row's go never approves a redirected item."""
    item = by_slug(items(state)).get(slug)
    if item is not None and item.redirect:
        raise Refused(
            f"refused: {slug} is {item.id}, which was redirected at {item.redirect}: no "
            f"approval of the row gives it a go until {item.id} is approved by its id, "
            f"jbus item approve {item.id} in the view or the command"
        )


def names(words: str, item: Item) -> bool:
    """Say whether the words name the item, by its id or its slug as a whole name."""
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
    basis: Basis | None = None,
) -> dict[str, Any]:
    """Record the user's go for an item, by its id. Return the `approved` line.

    `approve` takes a go from chat only when the words name the item and its risk is
    `routine`. The user approves a review item in the view, whose link the refusal names, and
    the same holds for an item that was redirected. The line has `by_id`, which ends a
    redirect (`Item.redirect`), and the word it rests on, when one is named (`rests`). When a
    steer died before it made the redirect's row change, `approve` makes that change before
    it ends the redirect (`_redirect`), under the same lock. Once the mark is gone, `settle`
    no longer looks at the item.
    """
    where = Where(where)
    if by != user.user:
        raise Refused(f"refused: only {user.user} approves an item, not {by}")
    said = f"approve by {by}" + (f": {words}" if words else "")
    more: dict[str, Any] = {"by_id": True, **({"words": words} if words else {}), **rests(basis)}
    with _locked(state):
        if where is Where.CHAT:
            _from_chat(state, id, words, project)
        _finish(state, id)
        made = _put(state, Verb.APPROVE, item=id, by=by, where=where, line=said, seen=seen, **more)
    told(box, made)
    return made


def _finish(state: Path, id: str) -> None:
    """Make the row change of the item's open redirect, when its line is written and the row
    has not changed. Do nothing when there is no redirect or the row has the change already."""
    item = items(state).get(id)
    if item is None or not item.redirect:
        return
    made = next((one for one in read(state) if one.get("id") == item.redirect), None)
    if made and made.get("brief") and item.slug:
        _redirect(state, made)


def _from_chat(state: Path, id: str, words: str, project: str) -> None:
    """Refuse an approval from chat when its words do not name the item, when the item is a
    review item, or when it was redirected. The caller holds `items.lock`, so no line comes
    between the check and the approval."""
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
    """Return what became of each message steer, by its line's id: the thread it went to,
    when, and why it waits when it has not gone. jbus only appends to the log, and a send is
    no move, so jbus keeps the sends beside the log, in `item-sends.json`."""
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
    """Send each message steer that has not gone to the thread of the item's home, through
    `word.post`. Each one goes as one queued message under the retry key
    `item|<project>|<id>|<line id>`, so when the command and a pass both send it, T3 Code
    takes it once. Return what became of each message it tried, by line id. `deliver` writes
    why a message waits once, and again when the reason changes, each time with a quiet
    event."""
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
        thread = thread_of(home)
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
    """Return the user's word that a steer names, read from where it is kept, or None when
    the steer names none."""
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
    """`jbus item steer`: make the steer, and for a message, say whether it went."""
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
    """Run `deliver` as a step of the pass, for each message steer T3 Code has not taken
    yet."""
    run = half.run
    went = deliver(run.state, run.box, run.home, half.client, run.user.user, run.now)
    for name, one in went.items():
        if one["sent_at"]:
            run.say(f"item {run.project.name}: message {name} sent to {one['thread']}")


def _settle(half: Any) -> None:
    """Run `settle` as a step of the pass, first in it, so a launch finds every redirect's row
    changed."""
    for said in settle(half.run.state):
        half.run.say(said)


STEPS = (
    verbs.Step("before-watch", 7, "item.settle", _settle),
    verbs.Step("before-watch", 15, "item.deliver", _deliver, ("client",)),
)
VERBS = (
    verbs.Verb("item", "work items: propose, approve, steer, drop, show, list", _arguments, _item),
)
