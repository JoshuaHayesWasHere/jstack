"""A scoped home reaches the root home only by a stop: `jbus stop`, which jbus takes only when the
home's own open row is held by something the home cannot clear.

Being stuck is a fact of the queue, so jbus checks it and reads no words. A stop names the scope's
own row and what holds it: `--on` another home's open row, by its slug or its pull request's `#<n>`,
or `--outside` something no home owns, such as the machine or Claude Code. jbus refuses a stop
unless:

- `--from` is the thread in a scoped home's `home-id`, and not the root's (`_scope`);
- the own row is in the queue, is that scope's by its stored brief's `Home:` line
  (`jbriefs.home.home_of`), and is not merged, done or removed;
- `--on` names a row of the queue that is not merged, done or removed, and is another home's: the
  root's or another scope's;
- no stop with the same key is open. The key is `stop|<scope>|<own row>|<on>`, where `<on>` is the
  slug of the row that holds it, or `outside`. So a row has one open stop on each row that holds it,
  and one on what is outside.

`stops.json` in the project's jbus state is a list of `Stop`. A taken stop goes at once, as one
message that needs `decide`, to the root's thread: `jbriefs.home.thread_of`, read when the message
goes and never kept, so a stop never reaches a thread that handed off. A stop that cannot go (no
root home is running, or its thread is capped, or T3 Code gave no answer) waits in the file, and
each pass tries it again (`deliver`). The message's retry key is the stop's key and the time it was
taken, so a stop taken again after its close is a new message and not a repeat of the old one.

The root answers with `jbus stop answer <scope> <own row> "<text>" --from <root id>`. The answer
closes the stop and goes as one message that needs `act` to the scope's thread, read when it goes,
and it waits as a stop does. A stop whose own row merges, is done or is removed closes itself on the
next pass, with no message (`settle`). A pass settles before it delivers, so a stop of a row that
just merged is not sent.

The verb and a pass can both hold the same unsent stop, so under `stops.lock` jbus rereads the file
and writes that a stop or an answer went only where it had not (`_change`). T3 Code takes a second
send with the same key as a repeat of the first.

A `decision` is not a stop: the user makes it, so a scoped home parks it as a gate (`jbus gate`).
The digest counts the `--outside` stops of each scope (`digest`), since those are the stops that no
row of the queue backs.
"""

from __future__ import annotations

import argparse
import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbriefs import home as homes
from jbus import Config, Refused, outbox, queue, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error

if TYPE_CHECKING:
    from jbus.cli import Half

NAME = "stops.json"
KIND = "stop"
ANSWER = "stop-answer"
OUTSIDE = "outside"
ENDED = {**{status: status for status in queue.FINAL}, "removed": "removed"}
ASKS = (
    "jbus: the {scope} home is stopped. Its row {row} is held by {held}, and it cannot clear that "
    "itself. What the root must clear: {what}\n\n"
    'Answer it once, with `jbus stop answer {scope} {row} "<your answer>" --from <this home\'s '
    "id>`, and jbus carries the answer to the {scope} home. A stop whose row merges or is removed "
    "closes itself."
)
ANSWERS = "jbus: the root home's answer to the {scope} home's stop on {row}: {answer}"
NO_ROOT = "no root home is running, its home-id holds no thread"
NO_SCOPE = "the {scope} home is not running, its home-id holds no thread"
NO_T3 = "jbus is not signed in to T3 Code"
NO_ANSWER = "T3 Code gave no answer"
CAPPED = "its thread is capped"


class Unparsable(Refused):
    """`stops.json` is not what this module writes, so jbus does not write over it."""


@dataclass(frozen=True)
class Stop:
    key: str
    scope: str
    row: str
    on: str
    outside: str
    what: str
    at: str
    thread: str = ""
    sent_at: str = ""
    waits: str = ""
    closed: str = ""
    closed_at: str = ""
    answer: str = ""
    answer_thread: str = ""
    answer_sent_at: str = ""
    answer_waits: str = ""

    @property
    def open(self) -> bool:
        return not self.closed


def path(state: Path) -> Path:
    return state / NAME


def key(scope: str, row: str, on: str) -> str:
    return f"{KIND}|{scope}|{row}|{on}"


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "stops.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load(state: Path) -> list[Stop]:
    """Return every stop of the project, oldest first. `load` takes no lock and writes nothing."""
    file = path(state)
    if not file.exists():
        return []
    try:
        return [Stop(**one) for one in json.loads(file.read_text())]
    except (OSError, ValueError, TypeError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error


def _write(state: Path, stops: list[Stop]) -> None:
    write_json(path(state), [asdict(one) for one in stops], mode=0o600)


def _stamp(run: Pass) -> str:
    """Return the time of the pass to the microsecond, so that two stops of one key, one closed
    and one taken in the same second, have two times."""
    return run.now.astimezone(UTC).isoformat()


def _scope(home: Path, thread: str) -> Path:
    """Return the directory of the scoped home whose thread `--from` is. Refuse the root's thread,
    and a thread that is no home's now."""
    if thread and thread == homes.thread_of(home):
        raise Refused("refused: --from is the root home's thread, and only a scoped home stops")
    for scope, _, _ in homes.scopes(home):
        if thread and homes.thread_of(scope) == thread:
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
    if row.get("status") in queue.FINAL:
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


def take(run: Pass, thread: str, row: str, on: str, outside: str, what: str) -> Stop:
    """Check a stop and keep it, or refuse it. `on` is the row or `#<n>` that holds the own row,
    and `outside` what holds it that no home owns: exactly one of the two is given."""
    what = " ".join(what.split())
    outside = " ".join(outside.split())
    if not what:
        raise Refused("refused: a stop says what the root must clear")
    if bool(on) == bool(outside):
        raise Refused("refused: a stop names what holds its row, --on <row or #pr> or --outside")
    scope = _scope(run.home, thread)
    _, mine = _open_row(run, row)
    if mine != scope:
        raise Refused(
            f"refused: {row} is the {_home_name(run.home, mine)} home's row, not the {scope.name} "
            "home's: a home stops only on its own row"
        )
    if on:
        on = _pulled(run, on.removeprefix("#")) if on.startswith("#") else on
        _, theirs = _open_row(run, on)
        if theirs == scope:
            raise Refused(
                f"refused: {on} is the {scope.name} home's own row, which it clears itself: "
                "a stop is on another home's row"
            )
    made = Stop(
        key(scope.name, row, on or OUTSIDE), scope.name, row, on, outside, what, _stamp(run)
    )
    with _locked(run.state):
        kept = load(run.state)
        if any(one.key == made.key and one.open for one in kept):
            raise Refused(f"refused: the stop {made.key} is already open, and the root has it")
        _write(run.state, [*kept, made])
    return made


def answer(run: Pass, thread: str, scope: str, row: str, text: str) -> Stop:
    """Close the open stops of a scope's row with the root's answer, and return the first. Refuse
    an answer from any thread but the root's, and one to a row with no open stop."""
    text = " ".join(text.split())
    if not text:
        raise Refused("refused: an answer has the root's words")
    root = homes.thread_of(run.home)
    if not root or thread != root:
        raise Refused(f"refused: --from {thread} is not the root home's thread, which answers")
    with _locked(run.state):
        kept = load(run.state)
        found = [one for one in kept if one.open and (one.scope, one.row) == (scope, row)]
        if not found:
            raise Refused(f"refused: the {scope} home has no open stop on {row}")
        closed = {
            one.key: replace(one, closed="answered", closed_at=_stamp(run), answer=text)
            for one in found
        }
        _write(run.state, [closed.get(one.key, one) if one.open else one for one in kept])
    return closed[found[0].key]


def _change(run: Pass, one: Stop, **changed: str) -> bool:
    """Write what became of a stop's message, and return whether it wrote anything. Leave a
    message that went after the caller read `one` as it is."""
    field = (
        "answer_sent_at" if "answer_sent_at" in changed or "answer_waits" in changed else "sent_at"
    )
    with _locked(run.state):
        kept = load(run.state)
        same = [each for each in kept if (each.key, each.at) == (one.key, one.at)]
        if not same or getattr(same[0], field):
            return False
        now = replace(same[0], **changed)
        _write(run.state, [now if each is same[0] else each for each in kept])
    return True


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
    return "" if went else CAPPED


def _held(run: Pass, one: Stop) -> str:
    if one.outside:
        return f"{one.outside}, which no home owns"
    whose = queue.brief(run.state, one.on) or ""
    return f"{one.on}, the {_home_name(run.home, homes.home_of(run.home, whose))} home's row"


def _ask(run: Pass, client: Client | None, one: Stop) -> None:
    thread = homes.thread_of(run.home)
    text = ASKS.format(scope=one.scope, row=one.row, held=_held(run, one), what=one.what)
    sent = f"{one.key}|{one.at}"
    waits = _send(run, client, thread, NO_ROOT, row=one.row, sent=sent, text=text, needs="decide")
    if not waits:
        if _change(run, one, thread=thread, sent_at=_stamp(run), waits=""):
            run.say(f"{KIND} {one.row}: sent to the root home at {thread}")
    elif waits != one.waits and _change(run, one, waits=waits):
        run.say(f"wait {one.row}: the {one.scope} home's stop waits, {waits}")


def _tell(run: Pass, client: Client | None, one: Stop) -> None:
    thread = homes.thread_of(run.home / one.scope)
    text = ANSWERS.format(scope=one.scope, row=one.row, answer=one.answer)
    sent = f"{ANSWER}|{one.scope}|{one.row}|{one.on or OUTSIDE}|{one.at}"
    gone = NO_SCOPE.format(scope=one.scope)
    waits = _send(run, client, thread, gone, row=one.row, sent=sent, text=text, needs="act")
    if not waits:
        if _change(run, one, answer_thread=thread, answer_sent_at=_stamp(run), answer_waits=""):
            run.say(f"{ANSWER} {one.row}: sent to the {one.scope} home at {thread}")
    elif waits != one.answer_waits and _change(run, one, answer_waits=waits):
        run.say(f"wait {one.row}: the root's answer to the {one.scope} home's stop waits, {waits}")


def settle(run: Pass) -> None:
    """Close each open stop whose own row merged, is done or was removed, with no message. A
    `queue.json` that does not parse closes nothing: a pass reports that file itself. With no
    stop open, `settle` reads no queue."""
    if not any(one.open for one in load(run.state)):
        return
    try:
        gone = queue.removed(run.state)
        rows = {row["slug"]: row for row in queue.load(run.state)}
    except queue.Unparsable:
        return
    with _locked(run.state):
        kept = load(run.state)
        ended = {}
        for one in kept:
            status = "removed" if one.row in gone else rows.get(one.row, {}).get("status", "")
            if one.open and status in ENDED:
                ended[id(one)] = replace(one, closed=ENDED[status], closed_at=_stamp(run))
        if ended:
            _write(run.state, [ended.get(id(one), one) for one in kept])
    for one in ended.values():
        run.say(f"{KIND} {one.row}: closed, the row is {one.closed}")


def deliver(run: Pass, client: Client | None) -> None:
    """Send each stop that waits to the root, and each answer that waits to its scope, once."""
    for one in load(run.state):
        if one.open and not one.sent_at:
            _ask(run, client, one)
        elif one.answer and not one.answer_sent_at:
            _tell(run, client, one)


def digest(state: Path, start: datetime) -> dict[str, Any]:
    """Return what the digest shows of the stops: each open one, and how many `--outside` stops
    each scope took at or after `start`. A `stops.json` that does not parse gives None."""
    try:
        kept = load(state)
    except Unparsable:
        return {"open": None, "outside": {}}
    outside: dict[str, int] = {}
    for one in kept:
        if one.outside and datetime.fromisoformat(one.at) >= start:
            outside[one.scope] = outside.get(one.scope, 0) + 1
    shown = ("scope", "row", "on", "outside", "what", "at", "sent_at", "waits")
    return {
        "open": [{column: getattr(one, column) for column in shown} for one in kept if one.open],
        "outside": outside,
    }


def _client(config: Config) -> Client | None:
    try:
        return Client(config.server, config.token_path)
    except Refused:
        return None


def _stop(args: argparse.Namespace, config: Config) -> int:
    """`jbus stop`: a scoped home's stop to the root, or the root's answer to one (`take`,
    `answer`). The command sends what it kept at once, and a pass sends what could not go."""
    run = Pass(config, verbs.project(config, args.project), datetime.now(UTC), lambda _: None)
    try:
        if args.row == "answer":
            if args.on is not None or args.outside is not None or len(args.words) < 3:
                raise Refused(
                    'refused: an answer is jbus stop answer <scope> <row> "<text>" --from <root id>'
                )
            scope, row, *words = args.words
            settle(run)
            one = answer(run, args.thread, scope, row, " ".join(words))
            deliver(run, _client(config))
            (now,) = [each for each in load(run.state) if (each.key, each.at) == (one.key, one.at)]
            to = now.answer_thread if now.answer_sent_at else f"nobody yet, {now.answer_waits}"
            print(f"answered: {one.key}, closed, the answer sent to {to}")
            return 0
        one = take(
            run, args.thread, args.row, args.on or "", args.outside or "", " ".join(args.words)
        )
        settle(run)
        deliver(run, _client(config))
        (now,) = [each for each in load(run.state) if (each.key, each.at) == (one.key, one.at)]
        to = f"the root home at {now.thread}" if now.sent_at else f"nobody yet, {now.waits}"
        print(f"stopped: {one.key}, sent to {to}")
        return 0
    except Refused as error:
        print(error)
        return 1


def _arguments(stop: argparse.ArgumentParser) -> None:
    stop.add_argument("row", help="this home's own open row, or `answer` for the root's answer")
    held = stop.add_mutually_exclusive_group()
    held.add_argument(
        "--on", metavar="ROW", help="the other home's open row, or #<n>, that holds it"
    )
    held.add_argument("--outside", metavar="WHAT", help="what holds it that no home owns")
    stop.add_argument(
        "--from",
        dest="thread",
        metavar="THREAD",
        required=True,
        help="this home's thread: a scoped home's for a stop, the root's for an answer",
    )
    stop.add_argument(
        "words",
        nargs="*",
        help="what the root must clear; for an answer, <scope> <row> and the root's words",
    )


VERBS = (
    verbs.Verb(
        "stop",
        "a scoped home's stop on its own row that another home's row holds, or the root's answer",
        _arguments,
        _stop,
    ),
)


def _pass(half: Half) -> None:
    """Close the stops whose rows ended, then send what waits. A `stops.json` that does not parse
    raises a gate, and the pass goes on."""
    try:
        settle(half.run)
        deliver(half.run, half.client)
    except Unparsable:
        half.run.gate(half.run.project.name, "stops.json does not parse", str(path(half.run.state)))


STEPS = (verbs.Step("before-watch", 12, "stop.deliver", _pass),)
