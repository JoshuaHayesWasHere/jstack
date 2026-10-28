"""Work items: jbus keeps every piece of work as one item with a stable id, a source, an owner
and one state, in `items.jsonl` in the project's state directory.

jbus names an item `w<n>`, with a number it mints from the project's counter (`items-next.json`), as
it mints a question's number. It never gives that name again, even if the log is lost. An item has a
slug only once a row of the queue links to it. An item proposed in chat has none. When
`jbus queue add` makes a row, the row links at once to the item that `--item` names, or to a new
item that the command mints.

The record is the log. jbus only ever appends to it, under `items.lock`, and never trims it:
`forget` trims `events.jsonl` and leaves the log alone. A line is `{id, item, at, by, where,
line, verb, ...}`. In it, `id` is the item's id and the line's number among the item's own
lines (`w3.2`), `where` is one of `Where`, and `line` says what happened. A `proposed` line
adds the item's `project`, `title` and `owner`, and its `slug` where it has one.

The state of an item is the fold of its lines by `MOVES` (`fold`). `MOVES` is one table of
every move there is. `write` refuses a move that is not in it, with a sentence, and writes
nothing. When an item leaves `waiting_on_you`, it goes back to the state it was in before, which
the fold records (`Item.back`). A writer may name the last line it saw (`seen`). Then `write`
refuses the new line if the item has moved since that line.

Each line is also a quiet event of its own kind, `item.<verb>`, in `events.jsonl`
(`wake.Box.record`), so the view's feed and `jbus events` show it.

The pass moves an item by its row (`follow`). It reads the row's approval (`approved`) and the
value `work.py` judged for the row this pass, and maps them to a state by `AIM`. It writes a
line only where the item is not in that state yet, and only for a move the facts show, so a pass
with nothing new writes nothing. Only `work.py` judges the row.

`risk` is `review` where a person must look before anything is done, and `routine` otherwise.

Each line is also a card for Sous Chef's chat, which `jbus.cards` makes and posts.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsettings
from jbus import (
    Refused,
    locked,
    party,
    passes,
    questions,
    queue,
    read_json,
    verbs,
    wake,
    work,
    write_json,
)

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
    """A `Verb` is what a line does to its item. Its value is the line's `verb`. It is also
    the part of the line's event kind that follows `item.`."""

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
LIVE = (S.PROPOSED, S.APPROVED, S.QUEUED, S.RUNNING, S.WAITING_ON_YOU, S.HELD)
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
    (S.HELD, Verb.DONE): S.DONE,
    (S.PROPOSED, Verb.DROP): S.DROPPED,
    (S.APPROVED, Verb.DROP): S.DROPPED,
    (S.QUEUED, Verb.DROP): S.DROPPED,
    (S.RUNNING, Verb.DROP): S.DROPPED,
    (S.WAITING_ON_YOU, Verb.DROP): S.DROPPED,
    (S.HELD, Verb.DROP): S.DROPPED,
}
"""Every move there is, one row each: from a state (None for an item not there yet), by a
verb, to a state, or to `BACK` for the state the item was in before `waiting_on_you`. An item
that is done or dropped takes none. A held item whose row merged anyway is done."""

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

SECRET = re.compile(rf"{party.door('changes access or secrets').named}|\bconfig(uration)?\b", re.I)
"""The words of an open gate that make its item a review: it is about a secret or the
config."""


@dataclass(frozen=True)
class Item:
    """An `Item` is one item, folded from its lines. `risk` is `routine` until a caller calls `risk`
    for the item. `back` is the state the item entered `waiting_on_you` from, and None in any other
    state."""

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
    """Return the sentence that refuses a move that is not in `MOVES`."""
    if item is None:
        return f"refused: there is no item {name}, and only a proposal makes one"
    return f"refused: {item.id} is {item.state}, and an item that is {item.state} cannot be {verb}"


def advance(item: Item | None, line: dict[str, Any]) -> Item:
    """Return the item after one line. Raise `Refused` where the line's move is not in `MOVES`,
    and `ValueError` where its verb is none of `Verb`."""
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
    back = None
    if state is S.WAITING_ON_YOU:
        back = item.back if item.state is S.WAITING_ON_YOU else item.state
    slug = line.get("slug", item.slug) if verb is Verb.LINK else item.slug
    return replace(item, state=state, back=back, slug=slug, last_event=line["id"])


def fold(lines: Iterable[dict[str, Any]]) -> dict[str, Item]:
    """Return every item, by its id, folded from its lines. Skip a line that is not a move:
    `write` never writes such a line now. A `steered` line, which jbus wrote before it had no
    steer, is such a line: it stays in the log, and `jbus item show` prints it."""
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
    """Return every line of the log, oldest first. Skip a line that does not parse, such as one
    that a writer left half written when its process died."""
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


def _number(name: str) -> int:
    digits = name.removeprefix("w")
    return int(digits) if name.startswith("w") and digits.isdigit() else 0


def _next(state: Path, lines: list[dict[str, Any]]) -> int:
    """Return the next number: past the counter and past every item the log names."""
    count = read_json(state / COUNTER, {}).get("next")
    highest = max((_number(str(line.get("item", ""))) for line in lines), default=0)
    return max(count if isinstance(count, int) else 1, highest + 1)


def reserve(state: Path) -> str:
    """Take a new item's id from the counter now, for a proposal that jbus writes after some
    other write. jbus never gives that id again, even where the proposal is never written."""
    with locked(state, LOCK):
        number = _next(state, read(state))
        write_json(state / COUNTER, {"next": number + 1})
    return f"w{number}"


def clock() -> datetime:
    """Return the time to write a line with."""
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
    """Append one line, and its event. Return the line.

    A `proposed` line makes the item that its `item` names, an id that `reserve` gave. A `proposed`
    line with no such id mints a new item. Any other line names its item. `write` refuses a line,
    with a sentence, where `MOVES` has no such move, or where `seen` is given and is not the item's
    last line. It also refuses a link where the item is linked already or another item has the slug.
    For a refused line, `write` writes nothing.
    """
    with locked(state, LOCK):
        made = _put(state, verb, item=item, by=by, where=where, line=line, seen=seen, **more)
    told(box, made)
    return made


def _current(lines: list[dict[str, Any]], name: str, verb: Verb, seen: str | None) -> Item:
    """Return the item to make a move on. Raise `Refused` when the item does not exist, when
    `seen` is given and is not the item's last line, or when the item's state has no such
    move.
    This function checks for a stale `seen` first. It refuses that with the line that came
    after `seen`, printed as `shown` prints a line. So when a move to `done` or `dropped`
    makes a go stale, the writer of that go learns of the move."""
    current = fold(lines).get(name)
    if current is None:
        raise Refused(refusal(None, verb, name))
    if seen is not None and seen != current.last_event:
        (last,) = [one for one in lines if one.get("id") == current.last_event][-1:]
        raise Refused(f"refused: {name} moved since {seen}: its last line is {said_line(last)}")
    if (current.state, verb) not in MOVES:
        raise Refused(refusal(current, verb))
    return current


def said_line(one: dict[str, Any]) -> str:
    """Format one line of the log as `jbus item show` prints it."""
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
    """Append `write`'s line, while the caller holds `items.lock`."""
    lines = read(state)
    found = fold(lines)
    if verb is Verb.PROPOSE:
        name = item or f"w{_next(state, lines)}"
        current = found.get(name)
        if current is not None:
            raise Refused(f"refused: {name} is proposed already")
    else:
        name = item
        current = _current(lines, name, verb, seen)
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
        "at": jsettings.stamp(clock()),
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
    """Write a line's quiet event in `events.jsonl`. This function writes it after the line, so
    if writing the event fails, the line stays in the log."""
    verb, name, slug = Verb(made["verb"]), made["item"], made.get("slug", "")
    said = f"item {box.project.name}: {name} {verb}" + (f", {slug}" if slug else "")
    box.record(kind(verb), f"{said}: {made['line']}", item=name, item_line=made["id"])


@dataclass(frozen=True)
class Basis:
    """A Basis names the user's words that a go is based on, the way an approval of a row
    names them (`queue.basis`): words said in the view, or a message of Sous Chef's chat."""

    kind: str
    ref: str
    said: queue.Said


def rests(basis: Basis | None) -> dict[str, Any]:
    """Return the fields that a line records about the user's word that the go cites, or
    nothing when the go cites no word."""
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
    link. Nothing reads them back from the chat, so the basis marks them `checked: false`."""
    said = queue.Said(" ".join(words.split()), user.stamp(now), "chat", False, message)
    return Basis("chat", message, said)


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
    """Record the user's go for an item, by its id, from the chat, the view or the command.
    Return the `approved` line. It has the word that the go cites, when the go names one
    (`rests`). A go from chat is taken only when its words name the item and the item's risk is
    `routine`: the user approves a review item in the view, and the refusal names the view's
    link."""
    where = Where(where)
    if by != user.user:
        raise Refused(f"refused: only {user.user} approves an item, not {by}")
    said = f"approve by {by}" + (f": {words}" if words else "")
    more: dict[str, Any] = {**({"words": words} if words else {}), **rests(basis)}
    with locked(state, LOCK):
        if where is Where.CHAT:
            _from_chat(state, id, words, project)
        made = _put(state, Verb.APPROVE, item=id, by=by, where=where, line=said, seen=seen, **more)
    told(box, made)
    return made


def _from_chat(state: Path, id: str, words: str, project: str) -> None:
    """Refuse a go from chat when its words do not name the item, or when the item is a review
    item. The caller holds `items.lock`, so no other writer adds a line between the check and
    the go."""
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


def risk(value: str, gates: Iterable[questions.Question]) -> Risk:
    """Return `review` for a merge `jmerge` holds (the value `hold`), and for an item with an
    open gate that has a `Holds:` line or words that name a secret or the config. A wait on
    the config shows up only as such a gate, since the `config` items of what waits on the
    user name no row. Return `routine` for anything else."""
    if value == "hold":
        return Risk.REVIEW
    for gate in gates:
        if gate.holds or SECRET.search(f"{gate.question} {gate.context}"):
            return Risk.REVIEW
    return Risk.ROUTINE


def judged(state: Path, item: Item) -> Item:
    """Return the item with its risk, from its row as the last pass left it."""
    if not item.slug:
        return item
    value = work.last(state).get(item.slug, "")
    gates = [one for one in questions.load(state) if one.slug == item.slug and not one.answer]
    return replace(item, risk=risk(value, gates))


def planned(item: Item | None, go: bool, value: str | None) -> list[Verb]:
    """Return the verbs a pass writes for an item, in order. They follow from its row's go and
    the value `work.py` judged for the row this pass (None where it confirmed no value).

    A pass approves an item that is proposed or held where the row has a go. Then the pass moves
    the item to the state `AIM` says, by the one move `MOVES` has for it. If the item waits on the
    user and its row no longer waits, the pass resumes it first. `MOVES` has that move only from
    the state the item came from. The pass makes no other move: it makes none that the facts do
    not show.
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


def follow(run: passes.Pass, rows: list[queue.Row]) -> int:
    """Move each row's item as `planned` says, give an item to a row that is not over and has
    none, and drop the item of a row that was removed. This is the pass's step. Return how many
    lines it wrote.

    A row can have an item with no line yet, where `jbus queue add` reserved the item and has
    not proposed it. The pass proposes that item, so the row has one item whichever writer
    comes first. Skip a line that `write` refused because another writer moved the item
    first: the next pass sees what that writer wrote.
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
    """Return a brief's title: its first line, after the `# <slug>:` it starts with."""
    first = (text or "").partition("\n")[0].removeprefix("#").strip()
    return first.removeprefix(f"{slug}:").strip() or slug


def link(state: Path, box: wake.Box, row: queue.Row, given: str, by: str, user: str) -> str:
    """Do what `jbus queue add` does to the row's item once the row is added: propose the item
    it reserved, or link the one `--item` named, and approve it where the row has a go. Return
    the item's id."""
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
    """Refuse an `--item` that cannot be linked to the row: one that does not exist, one that
    is another row's, and one whose state has no link."""
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
    """Return what `jbus item show` prints: the item, its risk, and each of its lines."""
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


STEPS = (
    verbs.Step(
        "after-derive", 50, "item.follow", lambda half: follow(half.run, half.table), ("rows",)
    ),
)
