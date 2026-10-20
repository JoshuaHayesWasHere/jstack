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

Each line is also a card for Sous Chef's chat (`card`): one body of the kind `item`, whose
`id` is the project and the line's id, so the relay sends each once and Sous Chef replaces the
item's card with the newest. A pass posts the lines no card went for yet (`post_cards`), to
each webhook route that is the relay (`relayed`), and a route's first pass posts one card for
each live item instead of the whole log.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import urllib.parse
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsettings
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
    "item.steered": "quiet",
    "item.sent": "quiet",
}
NAME = "items.jsonl"
LOCK = "items.lock"
COUNTER = "items-next.json"
SENDS = "item-sends.json"
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
    STEER = "steered"


class Steer(StrEnum):
    """What a steer does, the `action` of a `steered` line: a message to the item's home, a
    hold of its go, or a new brief that sends it back to `proposed`."""

    MESSAGE = "message"
    HOLD = "hold"
    REDIRECT = "redirect"


Move = Verb | Steer


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
LIVE = (S.PROPOSED, S.APPROVED, S.QUEUED, S.RUNNING, S.WAITING_ON_YOU, S.HELD)
MOVES: dict[tuple[State | None, Move], State | str] = {
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
    (S.HELD, Verb.DONE): S.DONE,
    (S.PROPOSED, Verb.DROP): S.DROPPED,
    (S.APPROVED, Verb.DROP): S.DROPPED,
    (S.QUEUED, Verb.DROP): S.DROPPED,
    (S.RUNNING, Verb.DROP): S.DROPPED,
    (S.WAITING_ON_YOU, Verb.DROP): S.DROPPED,
    (S.HELD, Verb.DROP): S.DROPPED,
    **{(state, Steer.MESSAGE): state for state in LIVE},
    (S.APPROVED, Steer.HOLD): S.HELD,
    (S.QUEUED, Steer.HOLD): S.HELD,
    (S.RUNNING, Steer.HOLD): S.HELD,
    (S.WAITING_ON_YOU, Steer.HOLD): S.HELD,
    (S.PROPOSED, Steer.REDIRECT): S.PROPOSED,
    (S.APPROVED, Steer.REDIRECT): S.PROPOSED,
    (S.QUEUED, Steer.REDIRECT): S.PROPOSED,
    (S.HELD, Steer.REDIRECT): S.PROPOSED,
}
"""Every move there is, one row each: from a state (None for an item not there yet), by a
verb or a steer's action, to a state, or to `BACK` for the state the item was in before
`waiting_on_you`. A message moves no item, and an item that is done or dropped takes none.
A running item is not redirected: its thread has the brief already, and a message steers it.
A held item whose row merged anyway is done."""

assert not {str(one) for one in Verb} & {str(one) for one in Steer}, "a steer is named as a verb"

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
    state `waiting_on_you` was entered from, and None in any other state. `redirect` is the
    id of the redirect that no approval by the item's id has followed yet (an `approved` line
    with `by_id`, which only `approve` writes), and empty where there is none. No rule, no
    word from chat, no approval of the row and no pass approves such an item (`jbus.steer`,
    `planned`)."""

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
    redirect: str = ""


def kind(verb: Verb) -> str:
    return f"item.{verb}"


def refusal(item: Item | None, move: Move, name: str = "") -> str:
    """The sentence a move that is not in `MOVES` is refused with."""
    if item is None:
        return f"refused: there is no item {name}, and only a proposal makes one"
    was = f"refused: {item.id} is {item.state}, and an item that is {item.state}"
    if isinstance(move, Steer):
        return f"{was} takes no {move}"
    return f"{was} cannot be {move}"


def move_of(line: dict[str, Any]) -> Move:
    """The move a line makes: its steer's action for a `steered` line, else its verb. A
    `steered` line with no action is the verb alone, which `MOVES` has no row for."""
    verb, action = Verb(line["verb"]), line.get("action")
    if verb is Verb.STEER and action in set(Steer):
        return Steer(action)
    return verb


def advance(item: Item | None, line: dict[str, Any]) -> Item:
    """The item after one line, or `Refused` where the line's move is not in `MOVES`."""
    verb, move = Verb(line["verb"]), move_of(line)
    to = MOVES.get((item.state if item else None, move))
    if to is None:
        raise Refused(refusal(item, move, line.get("item", "")))
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
    back = None
    if state is S.WAITING_ON_YOU:
        back = item.back if item.state is S.WAITING_ON_YOU else item.state
    slug = line.get("slug", item.slug) if verb is Verb.LINK else item.slug
    redirect = item.redirect
    if move is Steer.REDIRECT:
        redirect = line["id"]
    elif verb is Verb.APPROVE and line.get("by_id"):
        redirect = ""
    return replace(
        item, state=state, back=back, slug=slug, last_event=line["id"], redirect=redirect
    )


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
        made = _put(state, verb, item=item, by=by, where=where, line=line, seen=seen, **more)
    told(box, made)
    return made


def _current(lines: list[dict[str, Any]], name: str, move: Move, seen: str | None) -> Item:
    """The item a move is made on, or `Refused`: one there is not, one whose last line is
    not `seen` where that is given, and one whose state has no such move. A stale `seen` is
    refused first, with the line that came after it as `shown` prints a line, so a steer
    made stale by a move to `done` or `dropped` is told of that move."""
    current = fold(lines).get(name)
    if current is None:
        raise Refused(refusal(None, move, name))
    if seen is not None and seen != current.last_event:
        (last,) = [one for one in lines if one.get("id") == current.last_event][-1:]
        raise Refused(f"refused: {name} moved since {seen}: its last line is {said_line(last)}")
    if (current.state, move) not in MOVES:
        raise Refused(refusal(current, move))
    return current


def said_line(one: dict[str, Any]) -> str:
    """One line of the log as `jbus item show` prints it."""
    return f"{one['id']} {one['at']} {one['verb']} by {one['by']} in {one['where']}: {one['line']}"


def _put(
    state: Path,
    verb: Verb,
    *,
    item: str,
    by: str,
    where: Where,
    line: str,
    seen: str | None,
    **more: Any,
) -> dict[str, Any]:
    """`write`'s line, appended with `items.lock` held by the caller."""
    lines = read(state)
    found = fold(lines)
    if verb is Verb.PROPOSE:
        name = item or f"w{_next(state, lines)}"
        current = found.get(name)
        if current is not None:
            raise Refused(f"refused: {name} is proposed already")
    else:
        name = item
        current = _current(lines, name, move_of({"verb": verb, **more}), seen)
        if verb is Verb.APPROVE and current.redirect and not more.get("by_id"):
            raise Refused(
                f"refused: {name} was redirected at {current.redirect}, and only an approval "
                "by its id approves it"
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
    return made


def told(box: wake.Box, made: dict[str, Any]) -> None:
    """A line's quiet event, in `events.jsonl`. It is written after the line, so an event
    that cannot be written takes no line back."""
    verb, name, slug = Verb(made["verb"]), made["item"], made.get("slug", "")
    did = f"{verb} ({made['action']})" if verb is Verb.STEER else str(verb)
    said = f"item {box.project.name}: {name} {did}" + (f", {slug}" if slug else "")
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

    An item that is proposed or held is approved where the row has a go, but for one that
    was redirected and not approved by its id since. Then the item moves
    to the state `AIM` says, by the one move `MOVES` has for it. An item waiting on the user
    whose row no longer waits is resumed first, where only from the state it came from is
    there such a move. No other move is made: a pass makes none the facts do not show.
    """
    made: list[Verb] = []
    state, back = (item.state, item.back) if item else (S.PROPOSED, None)
    if go and state in (S.PROPOSED, S.HELD) and not (item and item.redirect):
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
    body = [f"  {said_line(one)}" for one in mine]
    return "\n".join(head + body) + "\n"


def listed(item: Item) -> str:
    return f"{item.id} {item.state} {item.risk} {item.slug or '-'} {item.title}"


CARD = "item"
CARDS = "cards.json"
VIEW_PORT = 4388
RELAY_PORT = 4390
LOOPBACK = ("127.0.0.1", "localhost", "::1")
ACTIONS: dict[Move, str] = {Verb.APPROVE: "approve", Steer.MESSAGE: "message", Steer.HOLD: "hold"}
"""What a card offers, in order, by the name its button sends as the `verb` of the relay's
`POST /item`."""
SAID: dict[Move, str] = {
    Verb.PROPOSE: "Proposed",
    Verb.LINK: "Linked to its row",
    Verb.APPROVE: "Approved",
    Verb.QUEUE: "Queued",
    Verb.LAUNCH: "Launched",
    Verb.WAIT: "Waiting on you",
    Verb.RESUME: "Resumed",
    Verb.HOLD: "Held",
    Verb.DONE: "Done",
    Verb.DROP: "Dropped",
    Verb.STEER: "Steered",
    Steer.MESSAGE: "Messaged",
    Steer.HOLD: "Held",
    Steer.REDIRECT: "Redirected",
}
SAID_IN = {Where.VIEW: " in jbus view", Where.CHAT: " in chat", Where.CLI: " from the command line"}


def actions(item: Item) -> list[str]:
    """What the card offers: nothing for a review item, which is decided in the view, and
    else each of `ACTIONS` that `MOVES` has from the item's state. A redirected item is
    approved only by its id in the view or the command, so its card offers no approval."""
    if item.risk is Risk.REVIEW:
        return []
    offered = [one for one in ACTIONS if (item.state, one) in MOVES]
    return [ACTIONS[one] for one in offered if not (one is Verb.APPROVE and item.redirect)]


def last(line: dict[str, Any], user: jsettings.Settings) -> str:
    """The line in one sentence for the card, as "Approved in jbus view by Josh, 11:52 EDT"."""
    where = Where(line["where"])
    said = f"{SAID[move_of(line)]}{SAID_IN.get(where, '')} by {line['by']}"
    return f"{said}, {user.clock(datetime.fromisoformat(line['at']))}"


def view_link(project: str, name: str) -> str:
    """The item's page in jbus view: at the first origin `JBUS_VIEW_ORIGINS` gives, the
    proxy the view is reached through, else at the first name `JBUS_VIEW_NAMES` gives, else
    the address `JBUS_VIEW_HOST` gives, else 127.0.0.1, at the view's port."""
    page = f"/#/{project}/item/{name}"
    origins = [one.strip() for one in os.environ.get("JBUS_VIEW_ORIGINS", "").split(",")]
    origin = next((one for one in origins if one), "")
    if origin:
        return origin.rstrip("/") + page
    names = [one.strip() for one in os.environ.get("JBUS_VIEW_NAMES", "").split(",")]
    host = next((one for one in names if one), os.environ.get("JBUS_VIEW_HOST") or "127.0.0.1")
    return f"http://{host}:{VIEW_PORT}{page}"


def card(item: Item, line: dict[str, Any], user: jsettings.Settings) -> dict[str, Any]:
    """The card of one line: the item as it stood after the line, with its risk now. Its
    `id` is the project and the line's id, since an item's id is the project's own."""
    return {
        "kind": CARD,
        "id": f"{item.project}.{line['id']}",
        "item": item.id,
        "project": item.project,
        "title": item.title,
        "state": str(item.state),
        "owner": item.owner,
        "risk": str(item.risk),
        "last": last(line, user),
        "actions": actions(item),
        "view": view_link(item.project, item.id),
    }


def relayed(route: wake.Route) -> bool:
    """Whether the route is the relay, on this machine at `RELAY_PORT` (4390, or the
    `RELAY_PORT` of the environment): the one door to Sous Chef's chat, where a card goes."""
    if not route.url or route.blocking:
        return False
    try:
        parts = urllib.parse.urlsplit(route.url)
        port = int(os.environ.get("RELAY_PORT") or RELAY_PORT)
        return parts.hostname in LOOPBACK and parts.port == port
    except ValueError:
        return False


def cards(
    state: Path, lines: list[dict[str, Any]], user: jsettings.Settings, after: int | None
) -> list[dict[str, Any]]:
    """The cards owed after the first `after` of the log's `lines`, in order. With None, no
    card went yet: one for each live item, at its last line, and not the whole log."""
    risks: dict[str, Risk] = {}
    found: dict[str, Item] = {}
    made: list[tuple[Item, dict[str, Any]]] = []
    for at, line in enumerate(lines):
        try:
            found[line["item"]] = advance(found.get(line["item"]), line)
        except (Refused, KeyError, ValueError, TypeError):
            continue
        if after is not None and at >= after:
            made.append((found[line["item"]], line))
    if after is None:
        by_id = {one.get("id"): one for one in lines}
        made = [(one, by_id[one.last_event]) for one in found.values() if one.state in LIVE]
    for one, _ in made:
        if one.id not in risks:
            risks[one.id] = judged(state, found[one.id]).risk
    return [card(replace(one, risk=risks[one.id]), line, user) for one, line in made]


def post_cards(run: wake.Pass) -> int:
    """The pass's step: post each card owed to each route that is the relay, in order, and
    keep in the route's `cards.json` how many lines of the log are carded. A POST that fails
    ends that route's turn, and the next pass posts from it again. The answer is how many
    went."""
    state, sent = run.state, 0
    for route in run.box.routes:
        if not relayed(route):
            continue
        mark = route.folder / CARDS
        after = read_json(mark, {}).get("carded")
        after = after if isinstance(after, int) else None
        lines = read(state)
        for one in cards(state, lines, run.user, after):
            why = wake._post(route, one)
            if why:
                run.say(f"cards {run.project.name}: card {one['id']} did not go: {why}")
                break
            sent += 1
        else:
            route.folder.mkdir(parents=True, exist_ok=True)
            write_json(mark, {"carded": len(lines)})
    return sent


STEPS = (
    verbs.Step(
        "after-derive", 50, "item.follow", lambda half: follow(half.run, half.table), ("rows",)
    ),
    verbs.Step("close", 80, "item.cards", lambda half: post_cards(half.run)),
)
