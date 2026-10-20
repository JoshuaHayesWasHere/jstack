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
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import jbus
import jsettings
from jbriefs import parse as briefs
from jbus import Refused, questions, queue, read_json, t3, verbs, wake, word, work, write_json

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
    word from chat, no approval of the row and no pass approves such an item (`approve`,
    `unruled`, `planned`)."""

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
    was redirected. Its line has `by_id`, which ends a redirect (`Item.redirect`).
    """
    where = Where(where)
    if by != user.user:
        raise Refused(f"refused: only {user.user} approves an item, not {by}")
    said = f"approve by {by}" + (f": {words}" if words else "")
    more: dict[str, Any] = {"by_id": True, **({"words": words} if words else {})}
    with _locked(state):
        if where is Where.CHAT:
            _from_chat(state, id, words, project)
        made = _put(state, Verb.APPROVE, item=id, by=by, where=where, line=said, seen=seen, **more)
    told(box, made)
    return made


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
    verbs.Step(
        "after-derive", 50, "item.follow", lambda half: follow(half.run, half.table), ("rows",)
    ),
)
VERBS = (
    verbs.Verb("item", "work items: propose, approve, steer, drop, show, list", _arguments, _item),
)
