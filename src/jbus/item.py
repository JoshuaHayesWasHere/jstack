"""Work items: every piece of work as one item with a stable id, a source, an owner and one
state, kept as `items.jsonl` in the project's state directory.

An item is named `w<n>`, minted from the project's counter (`items-next.json`, as a
question's number is) and never named again, also where the log was lost. It has a slug
only once a row of the queue is linked to it: an item proposed in chat has none, and a row
`jbus queue add` makes is linked at once, to the item `--item` names or to one it mints.

The record is the log, which is only ever appended to, under `items.lock`, and never
trimmed: `forget` trims `events.jsonl` and leaves it. A line is `{id, item, at, by, where,
line, verb, ...}`: `id` is the item's id and the line's number among the item's own lines
(`w3.2`), `where` is one of `Where`, `line` says what happened, and a `proposed` line adds
the item's `project`, `title` and `owner`, and its `slug` where it has one. The state of an
item is the fold of its lines by `MOVES` (`fold`), one table that holds every move there is:
what is not in it is refused in a sentence and writes nothing (`write`). `waiting_on_you` is
left for the state it was entered from, which the fold keeps (`Item.back`). A write may name
the last line its writer saw (`seen`), and is refused where the item moved since.

Each line is also a quiet event of its own kind, `item.<verb>`, in `events.jsonl`
(`wake.Box.record`), so the view's feed and `jbus events` show it.

The pass moves an item by its row (`follow`): the row's go (`approved`) and the value
`work.py` judged for it this pass, mapped to a state by `AIM`. It writes a line only where
that state is not the item's, and only a move the facts show: so a pass with nothing new
writes nothing. `work.py` stays the one judge of the row.

`risk` is `review` where a person must look before anything is done, and `routine` else.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import jbus
from jbus import Refused, questions, queue, read_json, verbs, wake, work, write_json

EVENTS = {
    "item.proposed": "quiet",
    "item.linked": "quiet",
    "item.approved": "quiet",
    "item.queued": "quiet",
    "item.launched": "quiet",
    "item.waiting": "quiet",
    "item.resumed": "quiet",
    "item.held": "quiet",
    "item.done": "quiet",
    "item.dropped": "quiet",
}
NAME = "items.jsonl"
LOCK = "items.lock"
COUNTER = "items-next.json"
OWNER = "home"
PASS_BY = "jbus"


class State(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_ON_YOU = "waiting_on_you"
    HELD = "held"
    DONE = "done"
    DROPPED = "dropped"


class Verb(StrEnum):
    """What a line does to its item. Its value is the line's `verb` and its event's kind
    after `item.`."""

    PROPOSE = "proposed"
    LINK = "linked"
    APPROVE = "approved"
    QUEUE = "queued"
    LAUNCH = "launched"
    WAIT = "waiting"
    RESUME = "resumed"
    HOLD = "held"
    DONE = "done"
    DROP = "dropped"


class Where(StrEnum):
    CHAT = "chat"
    VIEW = "view"
    CLI = "cli"
    PASS = "pass"


class Risk(StrEnum):
    ROUTINE = "routine"
    REVIEW = "review"


BACK = "the state it came from"

S = State
MOVES: dict[tuple[State | None, Verb], State | str] = {
    (None, Verb.PROPOSE): S.PROPOSED,
    (S.PROPOSED, Verb.LINK): S.PROPOSED,
    (S.APPROVED, Verb.LINK): S.APPROVED,
    (S.PROPOSED, Verb.APPROVE): S.APPROVED,
    (S.HELD, Verb.APPROVE): S.APPROVED,
    (S.APPROVED, Verb.QUEUE): S.QUEUED,
    (S.APPROVED, Verb.LAUNCH): S.RUNNING,
    (S.QUEUED, Verb.LAUNCH): S.RUNNING,
    (S.QUEUED, Verb.WAIT): S.WAITING_ON_YOU,
    (S.RUNNING, Verb.WAIT): S.WAITING_ON_YOU,
    (S.WAITING_ON_YOU, Verb.RESUME): BACK,
    (S.QUEUED, Verb.HOLD): S.HELD,
    (S.QUEUED, Verb.DONE): S.DONE,
    (S.RUNNING, Verb.DONE): S.DONE,
    (S.WAITING_ON_YOU, Verb.DONE): S.DONE,
    (S.PROPOSED, Verb.DROP): S.DROPPED,
    (S.APPROVED, Verb.DROP): S.DROPPED,
    (S.QUEUED, Verb.DROP): S.DROPPED,
    (S.RUNNING, Verb.DROP): S.DROPPED,
    (S.WAITING_ON_YOU, Verb.DROP): S.DROPPED,
    (S.HELD, Verb.DROP): S.DROPPED,
}
"""Every move there is, one row each: from a state (None for an item not there yet), by a
verb, to a state, or to `BACK` for the state the item was in before `waiting_on_you`."""

AIM: dict[str, State | None] = {
    "removed": None,
    "asking": S.WAITING_ON_YOU,
    "hung": S.RUNNING,
    "waiting": S.WAITING_ON_YOU,
    "merged": S.DONE,
    "leftover": None,
    "done": S.DONE,
    "closed": None,
    "result": S.RUNNING,
    "review": S.RUNNING,
    "findings": S.RUNNING,
    "second": S.RUNNING,
    "check": S.RUNNING,
    "proof": S.RUNNING,
    "rebase": S.RUNNING,
    "hold": S.WAITING_ON_YOU,
    "launching": S.RUNNING,
    "working": S.RUNNING,
    "quiet": S.RUNNING,
    "lost": S.RUNNING,
    "unapproved": S.HELD,
    "behind": S.QUEUED,
    "ready": S.QUEUED,
    "unknown": None,
}
"""The state each value of `work.VALUES` says an item is in, or None where it says nothing
of it. `waiting_on_you` is what is asked of the user: a gate, a thread's request, a merge
`jmerge` holds. A row with no go is `held` only where its item was queued: one that never
had a go is still proposed or approved."""

SECRET = re.compile(
    r"\b(secrets?|tokens?|credentials?|passwords?|api[ -]?keys?|config(uration)?)\b", re.I
)
"""The words of an open gate that make its item a review: it is about a secret or the
config."""


@dataclass(frozen=True)
class Item:
    """One item as its lines fold. `risk` is `routine` until `risk` is asked; `back` is the
    state `waiting_on_you` was entered from, and None in any other state."""

    id: str
    project: str
    slug: str
    title: str
    source: str
    owner: str
    state: State
    risk: Risk
    last_event: str
    back: State | None = None


def kind(verb: Verb) -> str:
    return f"item.{verb}"


def refusal(item: Item | None, verb: Verb, name: str = "") -> str:
    """The sentence a move that is not in `MOVES` is refused with."""
    if item is None:
        return f"refused: there is no item {name}, and only a proposal makes one"
    return f"refused: {item.id} is {item.state}, and an item that is {item.state} cannot be {verb}"


def advance(item: Item | None, line: dict[str, Any]) -> Item:
    """The item after one line, or `Refused` where the line's move is not in `MOVES`."""
    verb = Verb(line["verb"])
    to = MOVES.get((item.state if item else None, verb))
    if to is None:
        raise Refused(refusal(item, verb, line.get("item", "")))
    if item is None:
        return Item(
            id=line["item"],
            project=line.get("project", ""),
            slug=line.get("slug", ""),
            title=line.get("title", ""),
            source=line["where"],
            owner=line.get("owner", OWNER),
            state=State(to),
            risk=Risk.ROUTINE,
            last_event=line["id"],
        )
    state = item.back if to == BACK else State(to)
    assert state is not None
    back = item.state if state is S.WAITING_ON_YOU else None
    slug = line.get("slug", item.slug) if verb is Verb.LINK else item.slug
    return replace(item, state=state, back=back, slug=slug, last_event=line["id"])


def fold(lines: Iterable[dict[str, Any]]) -> dict[str, Item]:
    """Every item, by its id, as its lines fold. A line that is not a move is passed over:
    `write` writes none, so it was not written by jbus."""
    items: dict[str, Item] = {}
    for line in lines:
        try:
            items[line["item"]] = advance(items.get(line["item"]), line)
        except (Refused, KeyError, ValueError, TypeError):
            continue
    return items


def path(state: Path) -> Path:
    return state / NAME


def read(state: Path) -> list[dict[str, Any]]:
    """Every line of the log, oldest first. A line that does not parse, as one a write that
    died left half written, is passed over."""
    try:
        text = path(state).read_text()
    except FileNotFoundError:
        return []
    lines = []
    for one in text.splitlines():
        try:
            line = json.loads(one)
        except ValueError:
            continue
        if isinstance(line, dict):
            lines.append(line)
    return lines


def items(state: Path) -> dict[str, Item]:
    return fold(read(state))


def by_slug(found: dict[str, Item]) -> dict[str, Item]:
    return {one.slug: one for one in found.values() if one.slug}


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _number(name: str) -> int:
    digits = name.removeprefix("w")
    return int(digits) if name.startswith("w") and digits.isdigit() else 0


def _next(state: Path, lines: list[dict[str, Any]]) -> int:
    """The next number: past the counter and past every item the log names."""
    count = read_json(state / COUNTER, {}).get("next")
    highest = max((_number(str(line.get("item", ""))) for line in lines), default=0)
    return max(count if isinstance(count, int) else 1, highest + 1)


def reserve(state: Path) -> str:
    """A new item's id, taken from the counter now, for a proposal written after something
    else is: it is never given again, also where that proposal is never written."""
    with _locked(state):
        number = _next(state, read(state))
        write_json(state / COUNTER, {"next": number + 1})
    return f"w{number}"


def clock() -> datetime:
    """The time a line is written with."""
    return datetime.now(UTC)


def write(
    state: Path,
    box: wake.Box,
    verb: Verb,
    *,
    item: str = "",
    by: str,
    where: Where,
    line: str,
    seen: str | None = None,
    **more: Any,
) -> dict[str, Any]:
    """Append one line, and its event. The answer is the line.

    A `proposed` line makes the item `item` names, which `reserve` gave, or mints one. Any
    other names the item, and is refused in a sentence where `MOVES` has no such move, where
    the item's last line is not `seen` when that is given, and for a link, where the item is
    linked already or another item has the slug: a refused line writes nothing.
    """
    with _locked(state):
        lines = read(state)
        found = fold(lines)
        if verb is Verb.PROPOSE:
            name = item or f"w{_next(state, lines)}"
            current = found.get(name)
            if current is not None:
                raise Refused(f"refused: {name} is proposed already")
        else:
            name, current = item, found.get(item)
            if current is None:
                raise Refused(refusal(None, verb, item))
            if (current.state, verb) not in MOVES:
                raise Refused(refusal(current, verb))
            if seen is not None and seen != current.last_event:
                raise Refused(
                    f"refused: {name} moved since {seen}: its last line is {current.last_event}"
                )
        slug = more.get("slug", "")
        if slug:
            if current is not None and current.slug:
                raise Refused(f"refused: {name} is linked to {current.slug} already")
            other = by_slug(found).get(slug)
            if other is not None and other.id != name:
                raise Refused(f"refused: {slug} is linked to {other.id} already")
        count = sum(1 for one in lines if one.get("item") == name)
        made = {
            "id": f"{name}.{count + 1}",
            "item": name,
            "at": clock().astimezone(UTC).isoformat(timespec="seconds"),
            "by": by,
            "where": str(where),
            "line": line,
            "verb": str(verb),
            **more,
        }
        advance(current, made)
        handle = os.open(path(state), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(handle, (json.dumps(made, sort_keys=True) + "\n").encode())
        finally:
            os.close(handle)
        if verb is Verb.PROPOSE:
            count = read_json(state / COUNTER, {}).get("next")
            if not isinstance(count, int) or count <= _number(name):
                write_json(state / COUNTER, {"next": _number(name) + 1})
    told(box, made)
    return made


def told(box: wake.Box, made: dict[str, Any]) -> None:
    """A line's quiet event, in `events.jsonl`. It is written after the line, so an event
    that cannot be written takes no line back."""
    verb, name, slug = Verb(made["verb"]), made["item"], made.get("slug", "")
    said = f"item {box.project.name}: {name} {verb}" + (f", {slug}" if slug else "")
    box.record(kind(verb), f"{said}: {made['line']}", item=name, item_line=made["id"])


def risk(value: str, gates: Iterable[questions.Question]) -> Risk:
    """`review` for a merge `jmerge` holds (the value `hold`), and for an open gate of the
    item's with a `Holds:` line or whose words name a secret or the config, which is what a
    wait on the config is: the `config` items of what waits on the user name no row. Anything
    else is `routine`."""
    if value == "hold":
        return Risk.REVIEW
    for gate in gates:
        if gate.holds or SECRET.search(f"{gate.question} {gate.context}"):
            return Risk.REVIEW
    return Risk.ROUTINE


def judged(state: Path, item: Item) -> Item:
    """The item with its risk, from what the last pass left of its row."""
    if not item.slug:
        return item
    value = work.last(state).get(item.slug, "")
    gates = [one for one in questions.load(state) if one.slug == item.slug and not one.answer]
    return replace(item, risk=risk(value, gates))


def planned(item: Item | None, go: bool, value: str | None) -> list[Verb]:
    """The verbs a pass writes for an item, by its row's go and the value `work.py` judged
    for it this pass (None where it judged none it confirmed), in order.

    An item that is proposed or held is approved where the row has a go. Then the item moves
    to the state `AIM` says, by the one move `MOVES` has for it. An item waiting on the user
    whose row no longer waits is resumed first, where only from the state it came from is
    there such a move. No other move is made: a pass makes none the facts do not show.
    """
    made: list[Verb] = []
    state, back = (item.state, item.back) if item else (S.PROPOSED, None)
    if go and state in (S.PROPOSED, S.HELD):
        made.append(Verb.APPROVE)
        state = S.APPROVED
    target = AIM.get(value or "")
    if target is None or target is state:
        return made
    direct = _move(state, back, target)
    if direct is None and state is S.WAITING_ON_YOU and back is not None:
        after = _move(back, None, target)
        if after is not None:
            return [*made, Verb.RESUME, after]
    return [*made, direct] if direct else made


PASSED = (Verb.APPROVE, Verb.QUEUE, Verb.LAUNCH, Verb.WAIT, Verb.RESUME, Verb.HOLD, Verb.DONE)


def _move(state: State, back: State | None, target: State) -> Verb | None:
    for (start, verb), to in MOVES.items():
        if start is state and verb in PASSED and (back if to == BACK else to) is target:
            return verb
    return None


def follow(run: wake.Pass, rows: list[queue.Row]) -> int:
    """The pass's step: move each row's item as `planned` says, give a row that is not over
    and has no item one, and drop the item of a row that was removed. The answer is how many
    lines it wrote.

    A row has an item before its item's first line where `jbus queue add` reserved one and
    has not proposed it yet: the pass proposes that one, so the row has one item whoever
    writes first. A line refused since another writer moved the item first is passed over:
    the next pass sees what that writer wrote.
    """
    state, box = run.state, run.box
    found = items(state)
    linked = by_slug(found)
    kept = work.read(state) or {"work": []}
    values = {
        one["key"]: one["value"]
        for one in kept["work"]
        if isinstance(one, dict) and one.get("kind") == "row" and one.get("confirmed")
    }
    wrote = 0

    def put(verb: Verb, name: str, line: str, **more: Any) -> str:
        nonlocal wrote
        made = write(state, box, verb, item=name, by=PASS_BY, where=Where.PASS, line=line, **more)
        wrote += 1
        return made["item"]

    def moved(row: queue.Row) -> None:
        slug = row["slug"]
        item = linked.get(slug)
        value = values.get(slug)
        go = bool(row.get("approved")) and value != "unapproved"
        if item is None and queue.over(row):
            return
        if item is None:
            name = put(
                Verb.PROPOSE,
                row.get("item", ""),
                f"row {slug} had no item",
                project=run.project.name,
                title=_title(queue.brief(state, slug), slug),
                owner=OWNER,
                slug=slug,
            )
        else:
            name = item.id
        for verb in planned(item, go, value):
            if verb is Verb.APPROVE:
                line = f"row {slug} has a go: {queue.approval(row)}"
                put(verb, name, line, by_user=run.user.user)
            else:
                put(verb, name, f"row {slug} is {value}")

    for row in rows:
        try:
            moved(row)
        except Refused:
            continue
    gone = queue.removed_slugs(state)
    for item in found.values():
        if item.slug in gone and (item.state, Verb.DROP) in MOVES:
            try:
                put(Verb.DROP, item.id, f"row {item.slug} was removed")
            except Refused:
                continue
    return wrote


def _title(text: str | None, slug: str) -> str:
    """A brief's title: its first line, after the `# <slug>:` it starts with."""
    first = (text or "").partition("\n")[0].removeprefix("#").strip()
    return first.removeprefix(f"{slug}:").strip() or slug


def link(state: Path, box: wake.Box, row: queue.Row, given: str, by: str, user: str) -> str:
    """What `jbus queue add` does to the row's item, once the row is added: propose the item
    it reserved, or link the one `--item` named, and approve it where the row has a go. The
    answer is the item's id."""
    slug, name = row["slug"], row["item"]
    found = items(state).get(name)
    if found is None:
        text = queue.brief(state, slug)
        write(
            state,
            box,
            Verb.PROPOSE,
            item=name,
            by=by,
            where=Where.CLI,
            line=f"jbus queue add {slug}",
            project=box.project.name,
            title=_title(text, slug),
            owner=OWNER,
            slug=slug,
        )
    elif given and found.slug != slug:
        write(
            state, box, Verb.LINK, item=name, by=by, where=Where.CLI, line=f"row {slug}", slug=slug
        )
    now = items(state)[name]
    if row.get("approved") and now.state in (S.PROPOSED, S.HELD):
        line = f"row {slug} has a go: {queue.approval(row)}"
        write(state, box, Verb.APPROVE, item=name, by=by, where=Where.CLI, line=line, by_user=user)
    return name


def linkable(state: Path, given: str, slug: str) -> None:
    """Refuse an `--item` that cannot be linked to the row: one there is not, one that is
    another row's, and one whose state has no link."""
    found = items(state)
    item = found.get(given)
    if item is None:
        raise Refused(f"refused: there is no item {given}, and nothing is queued")
    if item.slug == slug:
        return
    if item.slug:
        raise Refused(f"refused: {given} is linked to {item.slug}, and nothing is queued")
    other = by_slug(found).get(slug)
    if other is not None:
        raise Refused(f"refused: {slug} is linked to {other.id}, and nothing is queued")
    if (item.state, Verb.LINK) not in MOVES:
        raise Refused(f"{refusal(item, Verb.LINK)}, and nothing is queued")


def shown(state: Path, item: Item) -> str:
    """What `jbus item show` prints: the item, its risk, and each of its lines."""
    item = judged(state, item)
    head = [
        f"{item.id}: {item.title}",
        f"state: {item.state}" + (f", from {item.back}" if item.back else ""),
        f"slug: {item.slug or '(none)'}",
        f"source: {item.source}",
        f"owner: {item.owner}",
        f"project: {item.project}",
        f"risk: {item.risk}",
        f"last event: {item.last_event}",
        "lines:",
    ]
    mine = [one for one in read(state) if one.get("item") == item.id]
    body = [
        f"  {one['id']} {one['at']} {one['verb']} by {one['by']} in {one['where']}: {one['line']}"
        for one in mine
    ]
    return "\n".join(head + body) + "\n"


def listed(item: Item) -> str:
    return f"{item.id} {item.state} {item.risk} {item.slug or '-'} {item.title}"


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
    if args.verb in ("approve", "drop"):
        verb = Verb.APPROVE if args.verb == "approve" else Verb.DROP
        if verb is Verb.APPROVE and args.by != config.user.user:
            raise Refused(f"refused: only {config.user.user} approves an item, not {args.by}")
        said = f"{args.verb} by {args.by}" + (f": {args.words}" if args.words else "")
        more = {"words": args.words} if args.words else {}
        where = Where(args.where)
        write(
            state,
            box,
            verb,
            item=args.id,
            by=args.by,
            where=where,
            line=said,
            seen=args.seen,
            **more,
        )
        print(f"{verb} {args.id}")
        return 0
    found = items(state)
    if args.verb == "show":
        if args.id not in found:
            raise Refused(f"refused: there is no item {args.id}")
        print(shown(state, found[args.id]), end="")
        return 0
    for one in sorted(found.values(), key=lambda one: _number(one.id)):
        print(listed(judged(state, one)))
    return 0


STEPS = (
    verbs.Step(
        "after-derive", 50, "item.follow", lambda half: follow(half.run, half.table), ("rows",)
    ),
)
VERBS = (verbs.Verb("item", "work items: propose, approve, drop, show, list", _arguments, _item),)
