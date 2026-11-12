"""A scoped home reaches the root home only by a stop: `jbus stop`, of one of three kinds
(`KINDS`, `--kind`). A `door` stop, the default, is taken only when the home's own open row is
held by something the home cannot clear, at a one-way door. A `decision` or a `go` stop is the
home's escalation of a choice it may not make alone, or of a go it may not give, on its own open
row or on an entry of its own plan (`--entry`).

A door stop carries a one-way door: `--holds` names one case of `features/home/templates/gates.md`
word for word (`party.CASES`). A door stop with no `--holds`, or with a case the table does not
have, is refused, and the refusal points the home at `--kind decision`. On a door stop the root
scouts if it needs facts and answers the stop with its recommendation, which the home adds to the
gate it parked for the door; the root writes nothing into a scope's files, and the user alone
opens or refuses the door.

A decision or a go stop takes no `--holds`, `--on` or `--outside`: nothing holds it but the root's
word. jbus refuses it unless its row is the scope's own and open, as a door's is, or its entry is
in the scope's `plan.md` (`plan.entries`). The root answers it with its own word (`jbus stop
answer`), which the home acts on: for a go on an entry that the user's standing word for goes
covers, the root gives the go first with `jbus plan go <entry> --scope <scope> --standing`. Or the
root passes it to the user with `jbus stop pass <scope> <row or entry> ["<recommendation>"] --from
<root id>` (`passed`). That closes each open decision and go stop of the row or entry as `passed`
and parks one gate for each, on the scope's own slug `home-<scope>` so `jbus needs` lists it under
that home, through `questions.park`. The gate holds for the user (`PASSED`), so silence never
closes it, and only the user's own word answers it. jbus tells the scope it was passed, and once
the user answers, carries the answer to the scope (`relay`). A door stop is never passed: its gate
is the home's own and holds already.

Being stuck is a fact of the queue, so jbus checks it and reads no words. A stop names the scope's
own row and what holds it: `--on` another home's open row, by its slug or its pull request's `#<n>`,
or `--outside` something no home owns, such as the machine or a sign-in. jbus refuses a stop
unless:

- for a door, `--holds` is a case of the gates table;
- `--from` is the thread in a scoped home's `home-id`, and not the root's (`_scope`);
- the own row is in the queue, is that scope's by its stored brief's `Home:` line
  (`jbriefs.home.home_of`), and is not merged, done or removed;
- `--on` names a row of the queue that is not merged, done or removed, and is another home's: the
  root's or another scope's;
- no stop with the same key is open. The key of a door stop is `stop|<scope>|<own row>|<on>`, where
  `<on>` is the slug of the row that holds it, or `outside`. So a row has one open stop on each row
  that holds it, and one on what is outside. The key of a decision or a go is `stop|<scope>|<own
  row>|a <kind>`, or `stop|<scope>|entry <entry>|a <kind>`: no slug has a space, so it is no door
  stop's key, and an entry and a row of the same slug have two keys.

`stops.json` in the project's jbus state holds three lists, `stops` of `Stop`, `answers` of `Answer`
and `tells` of `Tell` (`Kept`): each record is one message and what became of it. A taken stop goes
at once, as one message that needs `decide`, to the root's thread: `jbriefs.home.thread_of`, read
when the message goes and never kept, so a stop never reaches a thread that handed off. A stop that
cannot go (no root home is running, or the outbox holds it, or T3 Code gave no answer) waits in the
file, and each pass tries it again (`deliver`). The message's retry key is the stop's key and the
time it was taken, so a stop taken again after its close is a new message and not a repeat of the
old one.

The root answers with `jbus stop answer <scope> <own row> "<text>" --from <root id>`. The answer
closes every open stop of that row or entry, and goes as one message that needs `act` to the scope's
thread, read when it goes, however many stops it closed. It waits as a stop does. A stop whose own
row merges, is done or is removed, or whose entry left the plan, closes itself on the next pass,
with no message (`settle`), and so does the gate of a passed stop that still waits. A pass settles
before it delivers, so a stop of a row that just merged is not sent.

The verb and a pass can both hold the same unsent stop, so under `stops.lock` jbus rereads the file
and writes that a stop or an answer went only where it had not (`_change`). T3 Code takes a second
send with the same key as a repeat of the first.

The root steers a scope with no stop to answer by `jbus tell <scope> "<text>" --from <root id>`, or
`jbus tell every`, which keeps one `Tell` for each scoped home, oldest first in `tells`. Its words
are the root's own, never the user's: the message names them so, and is no go for any row, gate or
door. A scope that already holds the same words from the root, sent or not, holds them and keeps
none, so the command run again sends nothing twice. A tell goes as one message that needs `act`
under the retry key `tell|<scope>|<at>`, to the scope's thread read when it goes, so a scope that
handed off between the tell and the send gets it in its new thread. It waits as an answer does: a
scope with no `home-id` gets it on the first pass after its home starts and writes its id there.
An older jbus that writes `stops.json` drops `tells`, since it knows only the two lists.

The digest counts the `--outside` stops of each scope (`digest`), since those are the stops that no
row of the queue backs. The verb and the step of a pass are `jbus.stopverbs`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, Unpack

from jbriefs import home as homes
from jbriefs.home import thread_of
from jbus import (
    Refused,
    locked,
    outbox,
    party,
    plan,
    questions,
    queue,
    work,
    write_json,
)
from jbus.passes import Pass
from jbus.t3 import Client, T3Error

NAME = "stops.json"
LOCK = "stops.lock"
KIND = "stop"
ANSWER = "stop-answer"
TELL = "tell"
EVERY = "every"
OUTSIDE = "outside"
DOOR, DECISION, GO = "door", "decision", "go"
KINDS = (DOOR, DECISION, GO)
PASSED = "the root passed it to you"
"""What the gate of a passed stop holds for: no door of the table, but the user's own word."""
SAFE = "nothing is done on it until you answer"
ENDED = {**{status: status for status in work.FINAL}, "removed": "removed"}
ASKS = (
    "jbus: the {scope} home is stopped at a one-way door, {holds}. Its row {row} is held by "
    "{held}, and it cannot clear that itself. What the root must clear: {what}\n\n"
    "Scout if you need facts, then answer the stop with your recommendation, once, with "
    '`jbus stop answer {scope} {row} "<your recommendation>" --from <this home\'s id>`: jbus '
    "carries it to the {scope} home, which adds it to its own gate for the door. The root writes "
    "nothing into the {scope} home's files, and the user alone opens or refuses the door. A stop "
    "whose row merges or is removed closes itself."
)
ESCALATES = (
    "jbus: the {scope} home escalates a {kind} on {subject}: {what}\n\n"
    "{give}Answer it once, when it is within the user's standing word and the {scope} home's goal, "
    'with `jbus stop answer {scope} {slug} "<your word>" --from <this home\'s id>`: jbus carries '
    "it to the {scope} home, which acts on it. When it is the user's, pass it with `jbus stop pass "
    '{scope} {slug} "<your recommendation>" --from <this home\'s id>`: jbus parks a gate on '
    "home-{scope} that holds for the user's own answer, and carries that answer to the {scope} "
    "home. A stop whose row ends, or whose entry leaves the plan, closes itself."
)
GIVE = (
    "Where the user's standing word for goes covers it, give the go first with `jbus plan go "
    "{entry} --scope {scope} --standing --from <this home's id>`. "
)
ANSWERS = (
    "jbus: the root home's answer to the {scope} home's stop on {row}: {answer}\n\n"
    "Add it, as the root's recommendation, to your own gate for the door: the user alone opens or "
    "refuses the door."
)
TELLS = (
    "jbus: the root home's own message to the {scope} home, written by the root and not the "
    "user's word: {text}\n\n"
    "Take it as the root's steer. It is no go for any row, gate or door, and where it differs "
    "from the user's word, the user's word stands. Nothing is sent back for it."
)
WORD = (
    "jbus: the root home's answer to the {scope} home's {kind} on {subject}: {answer}\n\n"
    "It is the root's word, given within the user's standing word: act on it."
)
PASSES = (
    "jbus: the root home passed the {scope} home's {kind} on {subject} to the user, as question "
    "{number}, which holds for the user's own answer{said}. Do nothing on it until then: jbus "
    "carries the user's answer here."
)
USERS = (
    'jbus: the user answered question {number}, the {scope} home\'s {kind} on {subject}: "{words}"'
    "\n\nIt is the user's own word: act on it."
)
DIRECT = (
    "a door stop carries only a one-way door, --holds '<case>' with a case of "
    "features/home/templates/gates.md ({cases}): any other choice this home may not make alone "
    "goes to the root as --kind decision, and a go it may not give as --kind go"
)
GATE = """## Gate <n>: {what}
Status: open
Asked by: home-{scope}, thread {thread}
Default: {default}
Built on it: nothing: the {scope} home waits on {subject} for your answer
Undo: nothing to undo, since nothing is done on it
Context: the {scope} home escalated this {kind} on {subject} to the root home, which passed it to \
you{said}
Option: {option} (default, recommended): {default}
Option: your own: your words, which jbus carries to the {scope} home
"""
NO_ROOT = "no root home is running, its home-id holds no thread"
NO_SCOPE = "the {scope} home is not running, its home-id holds no thread"
NO_T3 = "jbus is not signed in to T3 Code"
NO_ANSWER = "T3 Code gave no answer"
HELD = "the outbox holds it, its thread capped or at work, and outbox.jsonl names the rule"
SHOWN = ("scope", "kind", "row", "entry", "on", "outside", "what", "at", "sent_at", "waits")
"""The columns of an open stop that the digest shows."""


class Unparsable(Refused):
    """`stops.json` is not what this module writes, so jbus does not write over it."""


@dataclass(frozen=True)
class Stop:
    """One stop, and its message to the root: the thread it went to, when, or why it waits.
    `kind` is one of `KINDS`; a record from before kinds is a door. `row` is the scope's own row,
    or empty for a stop on `entry`, an entry of the scope's plan. A stop the root passed keeps the
    number of the gate it parked (`question`), and when jbus was done with that gate's answer
    (`relayed`)."""

    key: str
    scope: str
    row: str
    on: str
    outside: str
    what: str
    at: str
    holds: str = ""
    thread: str = ""
    sent_at: str = ""
    waits: str = ""
    closed: str = ""
    closed_at: str = ""
    kind: str = DOOR
    entry: str = ""
    question: int = 0
    relayed: str = ""

    @property
    def open(self) -> bool:
        return not self.closed

    @property
    def slug(self) -> str:
        """The row or the entry the stop is on, as `answer` and `pass` name it."""
        return self.row or self.entry

    @property
    def subject(self) -> str:
        """The row or the entry the stop is on, in words."""
        return self.row or f"the entry {self.entry} of its plan"

    @property
    def sent(self) -> str:
        """The message's retry key: the stop's key and when it was taken."""
        return f"{self.key}|{self.at}"


@dataclass(frozen=True)
class Answer:
    """The root's answer to the open stops of one row or entry, `stops` by their keys, and its one
    message to the scope: `message`, or for a record from before it, `ANSWERS` with `text`. The
    same record carries the root's pass and the user's answer to a passed stop."""

    scope: str
    row: str
    text: str
    at: str
    stops: tuple[str, ...]
    thread: str = ""
    sent_at: str = ""
    waits: str = ""
    message: str = ""

    @property
    def sent(self) -> str:
        return f"{ANSWER}|{self.scope}|{self.row}|{self.at}"

    def said(self) -> str:
        return self.message or ANSWERS.format(scope=self.scope, row=self.row, answer=self.text)


@dataclass(frozen=True)
class Tell:
    """The root's own message to one scoped home, and what became of it."""

    scope: str
    text: str
    at: str
    thread: str = ""
    sent_at: str = ""
    waits: str = ""

    @property
    def sent(self) -> str:
        return f"{TELL}|{self.scope}|{self.at}"


Record = Stop | Answer | Tell
FIELDS: dict[type, str] = {Stop: "stops", Answer: "answers", Tell: "tells"}
"""The list of `Kept` that holds each kind of record."""


@dataclass(frozen=True)
class Kept:
    stops: tuple[Stop, ...] = ()
    answers: tuple[Answer, ...] = ()
    tells: tuple[Tell, ...] = ()


def path(state: Path) -> Path:
    return state / NAME


def key(scope: str, row: str, on: str) -> str:
    return f"{KIND}|{scope}|{row}|{on}"


def escalation(scope: str, row: str, entry: str, kind: str) -> str:
    """The key of a decision or a go: no slug has a space, so it is no door stop's key."""
    return key(scope, row or f"entry {entry}", f"a {kind}")


def load(state: Path) -> Kept:
    """Return every stop and answer of the project, oldest first. `load` takes no lock and writes
    nothing."""
    file = path(state)
    if not file.exists():
        return Kept()
    try:
        given = json.loads(file.read_text())
        return Kept(
            tuple(Stop(**one) for one in given["stops"]),
            tuple(Answer(**(one | {"stops": tuple(one["stops"])})) for one in given["answers"]),
            tuple(Tell(**one) for one in given.get("tells", [])),
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error


def _write(state: Path, kept: Kept) -> None:
    write_json(path(state), asdict(kept), mode=0o600)


def _stamp(run: Pass) -> str:
    """Return the time of the pass to the microsecond, so that two stops of one key, one closed
    and one taken in the same second, have two times."""
    return run.now.astimezone(UTC).isoformat()


def _scope(home: Path, thread: str) -> Path:
    """Return the directory of the scoped home whose thread `--from` is. Refuse the root's thread,
    and a thread that is no home's now."""
    if thread and thread == thread_of(home):
        raise Refused("refused: --from is the root home's thread, and only a scoped home stops")
    for scope, _, _ in homes.scopes(home):
        if thread and thread_of(scope) == thread:
            return scope
    raise Refused(f"refused: --from {thread} is no scoped home's thread now, in no home-id")


def _home_name(home: Path, directory: Path) -> str:
    return "root" if directory == home else directory.name


def _open_row(run: Pass, slug: str) -> tuple[queue.Row, Path]:
    """Return a row that is not merged, done or removed, with the directory of its home. Refuse
    any other."""
    gone = queue.was_removed(run.state, slug)
    if gone:
        raise Refused(f"refused: {gone}, so it holds nothing and nothing holds it")
    row, text = queue.current(run.state, slug)
    if row is None:
        raise Refused(f"refused: the queue has no row {slug}")
    if work.over(row):
        raise Refused(
            f"refused: {slug} is {row['status']}, so it holds nothing and nothing holds it"
        )
    return row, homes.home_of(run.home, text or "")


def _pulled(run: Pass, number: str) -> str:
    """Return the slug of the one row whose pull request is `#<number>`."""
    found = [row["slug"] for row in queue.load(run.state) if row.get("pr") == f"#{number}"]
    if len(found) != 1:
        said = "no row" if not found else f"{len(found)} rows, {', '.join(found)}"
        raise Refused(f"refused: --on #{number} is the pull request of {said}")
    return found[0]


def _door(holds: str) -> str:
    """Return the case of the gates table that `holds` names, or refuse it."""
    holds = " ".join(holds.split())
    if holds in party.CASES:
        return holds
    named = f"--holds '{holds}' is no case of the table" if holds else "this stop has no --holds"
    raise Refused(f"refused: {named}; {DIRECT.format(cases=', '.join(party.CASES))}")


def _entry(run: Pass, scope: Path, entry: str) -> None:
    """Refuse an entry that the scope's plan does not have, and a scope with no plan."""
    text = plan.path(run.home, scope.name).read_text()
    if not any(one.slug == entry for one in plan.entries(text)):
        raise Refused(f"refused: the {scope.name} home's plan has no entry {entry}")


def _own(run: Pass, scope: Path, row: str) -> None:
    """Refuse a row that is not the scope's own and open."""
    _, mine = _open_row(run, row)
    if mine != scope:
        raise Refused(
            f"refused: {row} is the {_home_name(run.home, mine)} home's row, not the {scope.name} "
            "home's: a home stops only on its own row"
        )


def take(
    run: Pass,
    thread: str,
    row: str,
    on: str,
    outside: str,
    what: str,
    holds: str = "",
    kind: str = DOOR,
    entry: str = "",
) -> Stop:
    """Check a stop and keep it, or refuse it. A door stop is on the scope's own `row`: `holds`
    is its one-way door, a case of the gates table, `on` the row or `#<n>` that holds the own row,
    and `outside` what holds it that no home owns, exactly one of the two. A decision or a go is
    on the own `row` or on `entry` of the scope's plan, and names none of the three."""
    what = " ".join(what.split())
    outside = " ".join(outside.split())
    if kind == DOOR:
        if entry:
            raise Refused("refused: a door stop is on the home's own row, not on --entry")
        holds = _door(holds)
    elif holds:
        raise Refused(
            "refused: a decision or a go holds for no door, so it takes no --holds: a one-way "
            "door is --kind door"
        )
    elif on or outside:
        raise Refused(
            "refused: a decision or a go names no --on or --outside: nothing holds it but the "
            "root's word"
        )
    if not what:
        raise Refused("refused: a stop says what the root must clear")
    if kind == DOOR and bool(on) == bool(outside):
        raise Refused("refused: a stop names what holds its row, --on <row or #pr> or --outside")
    scope = _scope(run.home, thread)
    if entry:
        _entry(run, scope, entry)
    else:
        _own(run, scope, row)
    if on:
        on = _pulled(run, on.removeprefix("#")) if on.startswith("#") else on
        _, theirs = _open_row(run, on)
        if theirs == scope:
            raise Refused(
                f"refused: {on} is the {scope.name} home's own row, which it clears itself: "
                "a stop is on another home's row"
            )
    named = (
        key(scope.name, row, on or OUTSIDE)
        if kind == DOOR
        else escalation(scope.name, row, entry, kind)
    )
    made = Stop(
        named,
        scope.name,
        "" if entry else row,
        on,
        outside,
        what,
        _stamp(run),
        holds,
        kind=kind,
        entry=entry,
    )
    with locked(run.state, LOCK):
        kept = load(run.state)
        if any(one.key == made.key and one.open for one in kept.stops):
            raise Refused(f"refused: the stop {made.key} is already open, and the root has it")
        _write(run.state, replace(kept, stops=(*kept.stops, made)))
    return made


def _root(run: Pass, thread: str, does: str) -> None:
    root = thread_of(run.home)
    if not root or thread != root:
        raise Refused(f"refused: --from {thread} is not the root home's thread, which {does}")


def _mine(kept: Kept, scope: str, slug: str, kinds: tuple[str, ...]) -> list[bool]:
    """Mark each stop that is open, of the scope, on the row or the entry `slug`, of `kinds`."""
    return [
        one.open and (one.scope, one.slug) == (scope, slug) and one.kind in kinds
        for one in kept.stops
    ]


def answer(run: Pass, thread: str, scope: str, row: str, text: str) -> Answer:
    """Close the open stops of a scope's row or entry with the root's answer, and return the
    answer. Refuse an answer from any thread but the root's, and one to a row or an entry with no
    open stop."""
    text = " ".join(text.split())
    if not text:
        raise Refused("refused: an answer has the root's words")
    _root(run, thread, "answers")
    at = _stamp(run)
    with locked(run.state, LOCK):
        kept = load(run.state)
        mine = _mine(kept, scope, row, KINDS)
        if not any(mine):
            raise Refused(f"refused: the {scope} home has no open stop on {row}")
        stops = tuple(
            replace(one, closed="answered", closed_at=at) if ours else one
            for one, ours in zip(kept.stops, mine, strict=True)
        )
        closed = [one for one, ours in zip(kept.stops, mine, strict=True) if ours]
        door = any(one.kind == DOOR for one in closed)
        first = closed[0]
        message = (
            ""
            if door
            else WORD.format(scope=scope, kind=first.kind, subject=first.subject, answer=text)
        )
        made = Answer(scope, row, text, at, tuple(one.key for one in closed), message=message)
        _write(run.state, replace(kept, stops=stops, answers=(*kept.answers, made)))
    return made


def tell(run: Pass, thread: str, to: str, text: str) -> list[tuple[Tell, bool]]:
    """Keep the root's message for the scope `to`, or for each scoped home with `every`, and return
    each scope's record with whether it is new. A scope that already holds the same words from the
    root keeps no second one. Refuse a tell from any thread but the root's, and to no scope."""
    text = " ".join(text.split())
    root = thread_of(run.home)
    if not root or thread != root:
        raise Refused(f"refused: --from {thread} is not the root home's thread, which tells")
    if not text:
        raise Refused("refused: a tell has the root's words")
    known = [scope.name for scope, _, _ in homes.scopes(run.home)]
    if to == EVERY and not known:
        raise Refused(f"refused: {run.project.name} has no scoped home for {EVERY}")
    if to != EVERY and to not in known:
        raise Refused(f"refused: {to} is no scoped home of {run.project.name}")
    at = _stamp(run)
    with locked(run.state, LOCK):
        kept = load(run.state)
        told = []
        for scope in known if to == EVERY else [to]:
            was = next((one for one in kept.tells if (one.scope, one.text) == (scope, text)), None)
            told.append((was, False) if was else (Tell(scope, text, at), True))
        made = tuple(one for one, new in told if new)
        if made:
            _write(run.state, replace(kept, tells=(*kept.tells, *made)))
    return told


def _gate(one: Stop, thread: str, text: str) -> str:
    """The lines of the gate a passed stop parks for the user, with the root's recommendation
    `text`, or none."""
    default = f"the root recommends: {text}; {SAFE}" if text else SAFE
    return GATE.format(
        what=f"{one.what} ({one.kind} on {one.slug}, from the {one.scope} home)",
        scope=one.scope,
        thread=thread or "none",
        default=default,
        subject=one.subject,
        kind=one.kind,
        said=f", and recommends: {text}" if text else "",
        option="the root's" if text else "wait",
    )


def passed(run: Pass, thread: str, scope: str, row: str, text: str) -> Answer:
    """Pass the open decision and go stops of a scope's row or entry to the user: park a gate
    that holds for each (`PASSED`) on `home-<scope>`, close each stop as `passed` with its gate's
    number, and return the message that tells the scope. `text` is the root's recommendation, or
    nothing. Refuse a pass from any thread but the root's, and one with no open decision or go
    stop on the row or the entry."""
    text = " ".join(text.split())
    _root(run, thread, "passes")
    asked = thread_of(run.home / scope)
    at = _stamp(run)
    with locked(run.state, LOCK):
        kept = load(run.state)
        mine = _mine(kept, scope, row, (DECISION, GO))
        if not any(mine):
            door = any(_mine(kept, scope, row, (DOOR,)))
            why = (
                ": a door stop is the user's already, through the home's own gate, so answer it"
                if door
                else ""
            )
            raise Refused(f"refused: the {scope} home has no open decision or go on {row}{why}")
        numbers: dict[str, int] = {}
        for one, ours in zip(kept.stops, mine, strict=True):
            if ours:
                gate, _ = questions.park(
                    run, f"home-{scope}", _gate(one, asked, text), (PASSED, SAFE)
                )
                numbers[one.key] = gate.number
        stops = tuple(
            replace(one, closed="passed", closed_at=at, question=numbers[one.key]) if ours else one
            for one, ours in zip(kept.stops, mine, strict=True)
        )
        first = next(one for one, ours in zip(kept.stops, mine, strict=True) if ours)
        message = PASSES.format(
            scope=scope,
            kind=first.kind,
            subject=first.subject,
            number=" and ".join(map(str, numbers.values())),
            said=f", with the root's recommendation: {text}" if text else "",
        )
        made = Answer(scope, row, text, at, tuple(numbers), message=message)
        _write(run.state, replace(kept, stops=stops, answers=(*kept.answers, made)))
    return made


def relay(run: Pass) -> None:
    """Carry the user's answer to each gate of a passed stop to the stop's scope, once, as a
    message of the same kind as the root's answer. A gate that a pass cleared is done with too,
    and carries nothing."""
    waiting = [one for one in load(run.state).stops if one.question and not one.relayed]
    if not waiting:
        return
    at = _stamp(run)
    with locked(run.state, LOCK):
        kept = load(run.state)
        made, stops = [], []
        for one in kept.stops:
            gate = questions.question(run.state, one.question) if one.question else None
            given = gate.answer if gate is not None else None
            if one.relayed or given is None or given.closed_by == questions.SILENCE:
                stops.append(one)
                continue
            if given.closed_by == questions.COMMAND:
                message = USERS.format(
                    number=one.question,
                    scope=one.scope,
                    kind=one.kind,
                    subject=one.subject,
                    words=given.words,
                )
                made.append(
                    Answer(one.scope, one.slug, given.words, at, (one.key,), message=message)
                )
            stops.append(replace(one, relayed=at))
        if made or stops != list(kept.stops):
            _write(run.state, replace(kept, stops=tuple(stops), answers=(*kept.answers, *made)))


class _Sent(TypedDict, total=False):
    thread: str
    sent_at: str
    waits: str


def _change(run: Pass, one: Record, **changed: Unpack[_Sent]) -> bool:
    """Write what became of a stop's, an answer's or a tell's message, and return whether it wrote
    anything. Leave a message that went after the caller read `one` as it is."""
    with locked(run.state, LOCK):
        kept = load(run.state)
        field = FIELDS[type(one)]
        records: tuple[Record, ...] = getattr(kept, field)
        same = [each for each in records if each.sent == one.sent]
        if not same or same[0].sent_at:
            return False
        now = replace(same[0], **changed)
        swapped: dict[str, Any] = {
            field: tuple(now if each is same[0] else each for each in records)
        }
        _write(run.state, replace(kept, **swapped))
    return True


def reread(state: Path, one: Record) -> Record:
    """Return the record of a stop, an answer or a tell as the file has it now."""
    kept = load(state)
    return next(each for each in getattr(kept, FIELDS[type(one)]) if each.sent == one.sent)


def _send(
    run: Pass,
    client: Client | None,
    thread: str,
    gone: str,
    *,
    row: str,
    sent: str,
    text: str,
    needs: outbox.Needs,
) -> str:
    """Send one message under its retry key, and return why it did not go, or nothing when it
    went. `gone` is why it waits when its home has no thread."""
    if not thread:
        return gone
    if client is None:
        return NO_T3
    template = sent.split("|")[0]
    try:
        went = outbox.send(
            run, client, thread=thread, row=row, key=sent, text=text, template=template, needs=needs
        )
    except T3Error:
        return NO_ANSWER
    return "" if went else HELD


def _held(run: Pass, one: Stop) -> str:
    if one.outside:
        return f"{one.outside}, which no home owns"
    whose = queue.brief(run.state, one.on) or ""
    return f"{one.on}, the {_home_name(run.home, homes.home_of(run.home, whose))} home's row"


def _asks(run: Pass, one: Stop) -> str:
    """The stop's message to the root."""
    if one.kind == DOOR:
        return ASKS.format(
            scope=one.scope, row=one.row, held=_held(run, one), what=one.what, holds=one.holds
        )
    give = GIVE.format(entry=one.entry, scope=one.scope) if one.kind == GO and one.entry else ""
    return ESCALATES.format(
        scope=one.scope,
        kind=one.kind,
        subject=one.subject,
        what=one.what,
        give=give,
        slug=one.slug,
    )


def _ask(run: Pass, client: Client | None, one: Stop) -> None:
    thread = thread_of(run.home)
    text = _asks(run, one)
    waits = _send(
        run, client, thread, NO_ROOT, row=one.slug, sent=one.sent, text=text, needs="decide"
    )
    if not waits:
        if _change(run, one, thread=thread, sent_at=_stamp(run), waits=""):
            run.say(f"{KIND} {one.slug}: sent to the root home at {thread}")
    elif waits != one.waits and _change(run, one, waits=waits):
        run.say(f"wait {one.slug}: the {one.scope} home's stop waits, {waits}")


def _tell(run: Pass, client: Client | None, one: Answer) -> None:
    thread = thread_of(run.home / one.scope)
    text = one.said()
    gone = NO_SCOPE.format(scope=one.scope)
    waits = _send(run, client, thread, gone, row=one.row, sent=one.sent, text=text, needs="act")
    if not waits:
        if _change(run, one, thread=thread, sent_at=_stamp(run), waits=""):
            run.say(f"{ANSWER} {one.row}: sent to the {one.scope} home at {thread}")
    elif waits != one.waits and _change(run, one, waits=waits):
        run.say(f"wait {one.row}: the root's answer to the {one.scope} home's stop waits, {waits}")


def _steer(run: Pass, client: Client | None, one: Tell) -> None:
    thread = thread_of(run.home / one.scope)
    text = TELLS.format(scope=one.scope, text=one.text)
    gone = NO_SCOPE.format(scope=one.scope)
    waits = _send(run, client, thread, gone, row="", sent=one.sent, text=text, needs="act")
    if not waits:
        if _change(run, one, thread=thread, sent_at=_stamp(run), waits=""):
            run.say(f"{TELL} {one.scope}: the root's message sent to its home, {thread}")
    elif waits != one.waits and _change(run, one, waits=waits):
        run.say(f"wait {one.scope}: the root's message to the {one.scope} home waits, {waits}")


def _planned(run: Pass, scope: str) -> set[str]:
    """The entries of a scope's plan now: none for a scope with no plan."""
    try:
        return {one.slug for one in plan.entries(plan.path(run.home, scope).read_text())}
    except (Refused, OSError):
        return set()


def _ended(run: Pass, stops: tuple[Stop, ...]) -> dict[str, str]:
    """Return how each stop's row or entry ended, by the stop's key: a row merged, done or
    removed, or an entry no longer in its scope's plan (`closed`). Read the plan of a scope only
    where it has a stop on an entry."""
    gone = queue.removed(run.state)
    rows = {row["slug"]: row for row in queue.load(run.state)}
    plans = {one.scope: _planned(run, one.scope) for one in stops if one.entry}
    ended = {}
    for one in stops:
        if one.entry:
            status = "" if one.entry in plans[one.scope] else "closed"
        else:
            status = "removed" if one.row in gone else rows.get(one.row, {}).get("status", "")
        if status in ENDED or status == "closed":
            ended[one.key + one.at] = ENDED.get(status, status)
    return ended


def settle(run: Pass) -> None:
    """Close each open stop whose own row merged, is done or was removed, or whose entry left its
    plan, with no message, and clear the gate of a passed stop that still waits when its row or
    entry ends so. A `queue.json` that does not parse closes nothing: a pass reports that file
    itself. With no stop open and no passed gate waiting, `settle` reads no queue."""
    kept = load(run.state)
    held = [one for one in kept.stops if one.question and not one.relayed]
    if not any(one.open for one in kept.stops) and not held:
        return
    try:
        ends = _ended(run, tuple(one for one in kept.stops if one.open or one in held))
    except queue.Unparsable:
        return
    with locked(run.state, LOCK):
        kept = load(run.state)
        ended = {}
        for one in kept.stops:
            end = ends.get(one.key + one.at)
            if one.open and end:
                ended[id(one)] = replace(one, closed=end, closed_at=_stamp(run))
        if ended:
            stops = tuple(ended.get(id(one), one) for one in kept.stops)
            _write(run.state, replace(kept, stops=stops))
    for one in ended.values():
        run.say(f"{KIND} {one.slug}: closed, the {'entry' if one.entry else 'row'} is {one.closed}")
    for one in held:
        end = ends.get(one.key + one.at)
        if end:
            words = f"the stop's {'entry' if one.entry else 'row'} {one.slug} is {end}"
            questions.clear(run, one.question, words)


def deliver(run: Pass, client: Client | None) -> None:
    """Send each stop that waits to the root, and each answer and tell that waits to its scope,
    once."""
    relay(run)
    kept = load(run.state)
    for one in kept.stops:
        if one.open and not one.sent_at:
            _ask(run, client, one)
    for given in kept.answers:
        if not given.sent_at:
            _tell(run, client, given)
    for told in kept.tells:
        if not told.sent_at:
            _steer(run, client, told)


def digest(state: Path, start: datetime) -> dict[str, Any]:
    """Return what the digest shows of the stops: each open one, and how many `--outside` stops
    each scope took at or after `start`. A `stops.json` that does not parse gives None."""
    try:
        kept = load(state).stops
    except Unparsable:
        return {"open": None, "outside": {}}
    outside: dict[str, int] = {}
    for one in kept:
        if one.outside and datetime.fromisoformat(one.at) >= start:
            outside[one.scope] = outside.get(one.scope, 0) + 1
    return {
        "open": [{column: getattr(one, column) for column in SHOWN} for one in kept if one.open],
        "outside": outside,
    }
