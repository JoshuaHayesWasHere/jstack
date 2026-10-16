"""A question for the user: one numbered record, written by `jbus gate` and closed by `jbus
answer`, and by nothing else.

`questions.json` in a project's state directory is `{"next", "records"}`. A record is a
`Question`:

- `number`: its own, unique among the questions of the project and never used twice. `next`
  only grows, and a new question is numbered above every gate a `gates.md` of the home has
  when it is asked. A home numbers its own gates with no look here, so one it makes later
  can have a question's number;
- `slug`: the brief or request that asked;
- `thread`: the asker's thread when it asked, by the `Thread:` line of that brief or request,
  or by the gate's own `Asked by:` line where the brief has none yet;
- `question` and `default`: the one line it asks, and what the thread did in place of an
  answer;
- `built_on` and `undo`: what rests on the default, and how to take it back;
- `context`: what the user needs to know to answer, from the gate's `Context:` line, or
  nothing;
- `options`: every option the thread weighed, in the order of its `Option:` lines. Each is
  an `Option`: its short `name`, what `follows` from it, whether it is the `default` that
  was taken, and whether it is the one the thread `recommended`. A record written before a
  gate had options has none;
- `holds` and `fail_safe`: the case of `HOLDS` the gate's `Holds:` line names, for a default
  that is irreversible or slow to revert, and the fail-safe its `Fail-safe:` line names. Both
  are empty for a gate whose thread acted on its default at once, and for a record written
  before gates had them;
- `proposed`: when a pass asked the thread of a question with no options to pipe them, or
  found that T3 Code no longer lists that thread. Nothing for a question never asked so;
- `asked_at`: when `jbus gate` took it;
- `answer`: nothing while it is open. Once closed, an `Answer`: `closed_by`, which is
  `jbus answer`, a home's `gates.md`, or `silence`; the user's `words`, `by` and `at`, `where` the
  command was run, and `keeps` for an answer that is the default; `told`, when a differing
  answer went to the asker; and `ref`, `said_in` and `checked`, which for an answer given as
  `--message` are the `<thread id>/<message id>` jbus read from T3 Code, that thread's
  title, and true, and for one typed with `--by` and `--at` are empty and false. One a home
  closed in its file has the file's
  `Status:` line as its `words`, the file as `where`, and no `by` and no `at`: jbus knows
  neither. One closed by silence has the words `default`, `by` jbus, `at` the pass that
  closed it, `where` "no answer in 2 hours", and `keeps`: it is not the user's word.

A gate is act-unless-stopped: the thread acts on its default at once, and the question is
the user's chance to stop it. A record is open until `jbus answer` closes it, and it is
closed once: a second answer is refused with the first one in the refusal. One thing more
closes it: a pass that finds it open 2 hours (`QUIET`) with no `Holds:` line closes it by
silence, with its default (`silent`). An answer of the user's still replaces that close,
as the one answer the record has, and one that differs is carried as any other.

A gate whose default is irreversible or slow to revert holds: its thread does not act, and
the question waits for the user. Its `Holds:` line names the case, one of `HOLDS`, and its
`Fail-safe:` line the dry-run, plan or bundle the user answers on. Such a gate is never
closed by silence. A `Holds:` line with no filled `Fail-safe:` line is refused, and so is an
unknown case, two `Holds:` lines, and a `Fail-safe:` line with no `Holds:` line.

While homes still keep a `gates.md`, one more thing closes a record: a pass that finds the
same gate in such a file with `Status: answered` (`closed_in_files`), since that home took
the answer and carried it.

A file that does not parse, or holds a record that is not one, is refused by every verb
that would write it (`Unparsable`): written back, it would lose the questions and give
their numbers out again. A pass says so in a gate, keeps the questions its list had, and
says no answered gate until the file can be read.

The same slug asking the same question again is the same record (`mirror.gate_key`), open
or closed. Asked again while it is open, the record takes the new default, undo and
built-on lines, its context and its options: a thread parks the same gate again at a later
head.

A gate proposes two options or more, one of them the default that was taken and the one
the thread recommends (`_proposed`).
One that does not is refused with `not sent` and the form of an `Option:` line whole, so a
thread whose skill is older than the options can mend its lines from the refusal alone. A
question that is open with no options was asked before that rule. A pass asks its thread,
once, to pipe the same gate again with them (`propose`): to the thread on the `Thread:`
line of the slug's brief or request, and to nobody where there is none or T3 Code no longer
lists it.

An answer that keeps the default asks nothing of anybody, but for a gate that holds: its
thread waits, so that answer is carried as a go-ahead (`GO`). One that differs is carried
(`carry`): one queued message to the thread on the `Thread:` line of the slug's brief or
request, with the words and the undo line, under the retry key `answer|<slug>|<number>`. It
is a `note`, a quiet event, so no answer starts a POST. The view sends an answer given on
its page at once, and the pass sends every one that is still owed (`tell`): an answer T3
Code refuses was not carried, which is a `gate`, once, and the pass sends it again until it
goes. `thread` is the
record of who asked and is never sent to: jbus sends only to a thread a brief or a request
names (`t3`).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jsettings
from jbus import Config, Refused, dispatch, mirror, queue, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused, typed
from jbus.wake import Pass

EVENTS = {"note": "quiet"}
NAME = "questions.json"
SOURCE = "jbus"
NOTE = "note"
NO_DEFAULT = (
    "refused: the gate has no Default: line, so it does not say what was done in place of an answer"
)
GO = (
    "jbus: {user} answered question {number} ({question}) with the default ({default}), which "
    'held for the answer ({holds}). The words, {at}: "{words}". Fail-safe: {fail_safe}. Go '
    "ahead with the default now, and add one line to the last Result or Report saying what "
    "you did. Then end your turn."
)
HELD = (
    "jbus: {user} answered question {number} ({question}), which held for the answer "
    '({holds}), and the answer is not the default ({default}). The words, {at}: "{words}". Do '
    "not take the default: do what the answer says, and add one line to the last Result or "
    "Report saying what you did. Then end your turn."
)
LINK = "has a conflict, and it is a link of a stack"
MESSAGE = (
    "jbus: {user} answered question {number} ({question}), and the answer is not the default "
    'you took ({default}). The words, {at}: "{words}". Undo: {undo}. Built on the default: '
    "{built_on}. Take the default back, do what the answer says, and add one line to the last "
    "Result or Report saying what you changed. Then end your turn."
)
_THREAD = re.compile(r"\bthread (\S+)")
_GROUP = re.compile(r"\([^()]*\)$")
COMMAND, HOME, SILENCE = "jbus answer", "gates.md", "silence"
QUIET = timedelta(hours=2)
UNANSWERED = "no answer in 2 hours"
HOLDS = (
    "deletes data",
    "rewrites history",
    "spends money",
    "touches prod or real users",
    "changes access or secrets",
    "publishes",
)
REFUSED = "T3 Code refused the answer to question {number}, so its thread was not told"
FORM = (
    'each option you weighed is one line, the default you took among them: "Option: <short '
    'name> (default, recommended): <what follows from it>", with both marks on the one that '
    "was taken, which is the one you recommend, and no mark on the rest"
)
NOT_SENT = "not sent: {what}. Write the options and pipe the gate again: " + FORM + "."
PROPOSE = (
    "jbus: question {number} is open and shows the user no options. Pipe its gate again to "
    "`jbus gate {slug}`: the lines below as they are, which are the ones jbus holds, so that "
    "it stays question {number}, and two things more under them. One line `Context: <what "
    "the user needs to know to answer, with the links to it>`. And " + FORM + ". Then end "
    "your turn.\n\n"
    "## Gate <n>: {question}\nStatus: open\nAsked by: {slug}, thread {thread}\n"
    "Default: {default}\nBuilt on it: {built_on}\nUndo: {undo}"
)


class Unparsable(Refused):
    """`questions.json` is not what this module writes, so nothing is written over it."""


@dataclass(frozen=True)
class Answer:
    words: str
    by: str
    at: str
    where: str
    keeps: bool
    told: str = ""
    closed_by: str = COMMAND
    ref: str = ""
    said_in: str = ""
    checked: bool = False

    def line(self) -> str:
        if self.closed_by == HOME:
            return f'closed by its home in {self.where}, "{self.words}"'
        if self.closed_by == SILENCE:
            return f"closed with its default by {self.by}, {self.at}: {self.where}"
        kind = "the default stands" if self.keeps else "not the default"
        return f'"{self.words}", by {self.by}, {self.at}, in {self.where} ({kind})'


@dataclass(frozen=True)
class Option:
    name: str
    follows: str
    default: bool = False
    recommended: bool = False


@dataclass(frozen=True)
class Question:
    number: int
    slug: str
    thread: str
    question: str
    default: str
    built_on: str
    undo: str
    asked_at: str
    answer: Answer | None = None
    context: str = ""
    options: tuple[Option, ...] = ()
    proposed: str = ""
    holds: str = ""
    fail_safe: str = ""

    @property
    def key(self) -> str:
        """What names the question however it arrived: piped, or read from a file."""
        return mirror.gate_key(self.slug, self.question)


def path(state: Path) -> Path:
    return state / NAME


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "questions.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _kept(state: Path) -> tuple[int, list[Question]]:
    """The counter and every record. No file is no record, and any other file that is not
    one this module wrote is `Unparsable`."""
    file = path(state)
    if not file.exists():
        return 1, []
    found = []
    try:
        kept = json.loads(file.read_text())
        for one in kept["records"]:
            answer = Answer(**one["answer"]) if one["answer"] else None
            options = tuple(Option(**each) for each in one.get("options", ()))
            found.append(Question(**{**one, "answer": answer, "options": options}))
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error
    highest = max((one.number for one in found), default=0)
    count = kept.get("next")
    return max(count if isinstance(count, int) else 1, highest + 1), found


def _write(state: Path, count: int, records: list[Question]) -> None:
    kept = {"next": count, "records": [asdict(one) for one in records]}
    write_json(path(state), kept, mode=0o600)


def load(state: Path) -> list[Question]:
    """Every record, open or closed, by number, or none where the file does not parse. It
    takes no lock and writes nothing."""
    try:
        return read(state)
    except Unparsable:
        return []


def read(state: Path) -> list[Question]:
    """Every record, as `load` gives them, or `Unparsable` for a file that is not one."""
    return _kept(state)[1]


def _floor(home: Path) -> int:
    """One past the highest number a gate has in the home's `gates.md` or a scoped home's."""
    numbers = (number for _, number, *_ in mirror.home_gates(home) if number.isdigit())
    return max([0, *map(int, numbers)]) + 1


def thread_of(home: Path, slug: str) -> str:
    """The thread on the `Thread:` line of the slug's brief, or of its request."""
    for kind in ("tasks", "scouts"):
        try:
            found = dispatch.thread_of((home / kind / f"{slug}.md").read_text(errors="replace"))
        except OSError:
            continue
        if found:
            return found
    return ""


def _count(number: int, noun: str) -> str:
    words = ("no", "one", "two", "three")
    return f"{words[number] if number < len(words) else number} {noun}{'' if number == 1 else 's'}"


def _proposed(lines: str) -> tuple[Option, ...]:
    """The options of a gate's lines, or `Refused` with what they lack.

    The user picks among what the thread weighed, so a gate has two options or more, each
    under a name of its own. One of them is the default that was taken, and at most one is
    the thread's pick. A name that ends in parentheses is a mark that was not spelled as one,
    and kept as a name it would be an option with no mark. The default that was taken is
    the one the thread recommends: a pass may close the question with it by silence.
    """
    read, unread = mirror.options(lines)
    found = tuple(
        Option(name, follows, mirror.DEFAULT in marks, mirror.RECOMMENDED in marks)
        for name, follows, marks in read
    )
    names = [one.name for one in found]
    twice = sorted({name for name in names if names.count(name) > 1})
    taken = sum(one.default for one in found)
    picked = sum(one.recommended for one in found)
    odd = [one.name for one in found if _GROUP.search(one.name)]
    if unread:
        what = f'the line "{unread[0]}" is not an option\'s short name and what follows from it'
    elif odd:
        what = (
            f'the name "{odd[0]}" ends in parentheses that are not (default), (recommended) '
            "or (default, recommended)"
        )
    elif len(found) < 2:
        what = f"the gate has {_count(len(found), 'Option: line')} and needs two or more"
    elif twice:
        what = f'two options have the name "{twice[0]}"'
    elif taken != 1:
        marked = "no option is" if not taken else f"{_count(taken, 'option')} are"
        what = f"{marked} marked (default), and one is the default that was taken"
    elif picked > 1:
        what = f"{_count(picked, 'option')} are marked (recommended), and one is the pick"
    elif not picked:
        what = (
            "no option is marked (recommended), and the default that was taken is the one "
            "recommended"
        )
    elif (pick := next(one for one in found if one.recommended)) and not pick.default:
        taken_name = next(one.name for one in found if one.default)
        what = (
            f"the option marked (recommended) is {pick.name}, and the default that was taken "
            f"is {taken_name}: mark the default (default, recommended)"
        )
    else:
        return found
    raise Refused(NOT_SENT.format(what=what))


def _held(lines: str) -> tuple[str, str]:
    """The case a gate's `Holds:` line names and the fail-safe of its `Fail-safe:` line, both
    empty for a gate that acts at once, or `Refused` with what is wrong with them."""
    said = {
        name: [
            line[len(name) + 1 :].strip()
            for line in lines.splitlines()
            if line.startswith(f"{name}:")
        ]
        for name in ("Holds", "Fail-safe")
    }
    holds, safe = said["Holds"], said["Fail-safe"]
    cases = " | ".join(HOLDS)
    if len(holds) > 1 or len(safe) > 1:
        what = f"the gate has two {'Holds' if len(holds) > 1 else 'Fail-safe'}: lines"
    elif holds and holds[0] not in HOLDS:
        what = f'the Holds: line says "{holds[0]}", and a gate that holds names one of: {cases}'
    elif holds and (not safe or not safe[0] or safe[0].startswith("<")):
        what = (
            f"the gate holds ({holds[0]}) and has no Fail-safe: line, which names the dry-run, "
            "plan or bundle the user answers on"
        )
    elif safe and not holds:
        what = (
            f"the gate has a Fail-safe: line and no Holds: line: add Holds: <{cases}>, or take "
            "the Fail-safe: line out of a gate whose default acts at once"
        )
    else:
        return (holds[0], safe[0]) if holds else ("", "")
    raise Refused(f"not sent: {what}.")


def ask(state: Path, home: Path, slug: str, lines: str, now: datetime) -> tuple[Question, bool]:
    """Keep the gate a thread piped. The answer is its record, and whether it is new.

    Lines with no `Default:` line that is filled in are refused: a question with no default
    is a thread that waits, and no record says what an answer would undo. So are lines that
    do not propose two options with the default among them as the one recommended
    (`_proposed`), and a `Holds:` line that is wrong (`_held`).
    """
    asked, default = mirror.question(lines), mirror.field(lines, "Default")
    if not default or default.startswith("<"):
        raise Refused(NO_DEFAULT)
    options = _proposed(lines)
    holds, fail_safe = _held(lines)
    named = _THREAD.search(mirror.field(lines, "Asked by"))
    with _locked(state):
        count, records = _kept(state)
        key = mirror.gate_key(slug, asked)
        said = {
            "thread": thread_of(home, slug) or (named[1] if named else ""),
            "default": default,
            "built_on": mirror.field(lines, "Built on it"),
            "undo": mirror.field(lines, "Undo"),
            "context": mirror.context(lines),
            "options": options,
            "holds": holds,
            "fail_safe": fail_safe,
        }
        for one in records:
            if one.key == key:
                again = one if one.answer else replace(one, **said)
                if again != one:
                    _write(state, count, [again if each is one else each for each in records])
                return again, False
        number = max(count, _floor(home))
        at = now.astimezone(UTC).isoformat(timespec="seconds")
        made = Question(number=number, slug=slug, question=asked, asked_at=at, **said)
        _write(state, number + 1, [*records, made])
    return made, True


def answer(
    state: Path,
    number: int,
    words: str,
    *,
    by: str,
    at: str,
    where: str,
    keeps: bool,
    user: jsettings.Settings,
    heard: queue.Said | None = None,
) -> Question:
    """Close a question with the user's answer. A second answer is refused, with the first,
    but for a close by silence: that is no answer of the user's, and theirs replaces it.

    `keeps` says the answer is the default. Only the one who heard the answer knows: words
    such as "yes" do not say it. `heard` is the message jbus read the words and the time
    from, for an answer given as `--message`.
    """
    if by != user.user:
        raise Refused(f"refused: only {user.user} answers a question, not {by}")
    if not user.takes(at):
        raise Refused(f'refused: --at is "{user.form(at)}"')
    if not words.strip():
        raise Refused("refused: an answer has the user's words")
    with _locked(state):
        count, records = _kept(state)
        found = [one for one in records if one.number == number]
        if not found:
            numbers = ", ".join(str(one.number) for one in records if one.answer is None)
            raise Refused(f"refused: no question {number}, open: {numbers or 'none'}")
        (one,) = found
        if one.answer and one.answer.closed_by != SILENCE:
            raise Refused(f"refused: question {number} was answered already: {one.answer.line()}")
        given = Answer(" ".join(words.split()), by, at, where, keeps)
        if heard:
            given = replace(given, ref=heard.ref, said_in=heard.said_in, checked=heard.checked)
        closed = replace(one, answer=given)
        _write(state, count, [closed if each.number == number else each for each in records])
    return closed


def basis(state: Path, ref: str) -> queue.Said:
    """The answer that closed the question of that number, as what an approval rests on.

    A question that is open, or one a home closed in its own file, holds no words of the
    user's with a time, and is refused.
    """
    found = [one for one in read(state) if str(one.number) == ref]
    if not found:
        raise Refused(f"refused: {path(state)} has no question {ref}")
    given = found[0].answer
    if given is None:
        raise Refused(f"refused: question {ref} is open, and an open question approves nothing")
    if given.closed_by != COMMAND:
        raise Refused(f"refused: question {ref} was {given.line()}: jbus has no word of it")
    return queue.Said(given.words, given.at, given.said_in, given.checked, given.ref)


def _told(state: Path, number: int, how: str) -> None:
    with _locked(state):
        count, records = _kept(state)
        records = [
            replace(one, answer=replace(one.answer, told=how))
            if one.number == number and one.answer
            else one
            for one in records
        ]
        _write(state, count, records)


def closed_in_files(run: Pass) -> None:
    """Close each open question whose gate a `gates.md` of the home has as answered.

    Until the skills read jbus, a home that takes an answer in its own thread writes it in
    its `gates.md` and carries it itself. So the record closes with the words of that
    `Status:` line, and nothing is sent. Those words replace a close by silence.
    """
    answered = {
        key: (mirror.field(body, "Status"), file)
        for file, _, _, body, key in mirror.home_gates(run.home)
        if mirror.field(body, "Status").startswith("answered")
    }
    if not answered or not any(_open(one) for one in load(run.state)):
        return
    with _locked(run.state):
        count, records = _kept(run.state)
        closed = []
        for one in records:
            if _open(one) and one.key in answered:
                status, file = answered[one.key]
                given = Answer(status, "", "", str(file), False, closed_by=HOME)
                one = replace(one, answer=given)
            closed.append(one)
        if closed != records:
            _write(run.state, count, closed)


def _open(one: Question) -> bool:
    """Whether a record waits for an answer: open, or closed by silence alone."""
    return one.answer is None or one.answer.closed_by == SILENCE


def silent(run: Pass) -> None:
    """Close by silence each open question with no `Holds:` line that has been open 2 hours
    or more (`QUIET`), with its default: its thread acted on it when it asked, so nothing is
    sent. A quiet `note` event says so, once for the question."""
    if not path(run.state).exists():
        return
    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    given = Answer("default", SOURCE, at, UNANSWERED, True, closed_by=SILENCE)
    with _locked(run.state):
        try:
            count, records = _kept(run.state)
        except Unparsable:
            return
        closed = [replace(one, answer=given) if _quiet(one, run.now) else one for one in records]
        if closed == records:
            return
        _write(run.state, count, closed)
    for was, one in zip(records, closed, strict=True):
        if was is not one:
            line = f"{NOTE} {one.slug}: question {one.number} closed with its default, {UNANSWERED}"
            run.find(one.slug, NOTE, line, key=f"silence {one.number}")
            run.say(line)


def _quiet(one: Question, now: datetime) -> bool:
    """Whether silence closes the question now. A gate that holds waits for the user, and a
    link's conflict asks its home and not the user, so neither is ever closed this way."""
    if one.answer or one.holds or one.question.endswith(LINK):
        return False
    try:
        asked = datetime.fromisoformat(one.asked_at)
    except ValueError:
        return False
    return asked.tzinfo is not None and now - asked >= QUIET


def _state(one: Question) -> str:
    """What the line of a waiting question adds: that its default holds for the answer, with
    the fail-safe, or that it was acted on already. A link's conflict, which asks its home,
    says neither."""
    if one.holds:
        return f" It holds ({one.holds}) for your answer, with its fail-safe: {one.fail_safe}."
    if not one.question.endswith(LINK):
        return " Its default is acted on already, and stands unless you stop it."
    return ""


def item(one: Question) -> dict[str, Any]:
    """An open question as the list of what waits on the user has a gate: `acted` where its
    thread acted on the default at once, and the case and fail-safe of one that holds."""
    return {
        "kind": "gate",
        "key": f"gate:q{one.number}",
        "source": SOURCE,
        "line": f"question {one.number}: {one.question}{_state(one)}",
        "number": str(one.number),
        "question": one.question,
        "default": one.default,
        "home": "",
        "slug": one.slug,
        "since": one.asked_at,
        "acted": not one.holds,
        "holds": one.holds,
        "fail_safe": one.fail_safe,
    }


def listed(item: dict[str, Any]) -> bool:
    """Whether an item of the list of what waits on the user is a question of this file."""
    return item.get("source") == SOURCE


@dataclass(frozen=True)
class Carried:
    """What became of one answer that was to go to its asker: `told` where it went, and
    `thread` where it had one to go to. `error` is what T3 Code said where it did not take
    it, and `refused` says that it answered and refused."""

    message: str = ""
    thread: str = ""
    told: bool = False
    error: str = ""
    refused: bool = False


def carry(run: Pass, client: Client, one: Question) -> Carried:
    """Send one answer that differs from its default to the thread that asked, or one that
    keeps the default of a gate that holds: that thread waits for it to go ahead (`GO`), or
    for one that differs, not to take the default (`HELD`).

    It is one queued message to the thread on the `Thread:` line of the slug's brief or
    request, under the retry key `answer|<slug>|<number>`: the pass and the view both send
    through here, so an answer one of them sent is sent by neither again. One that went is
    marked `told` on its record and is a quiet event. One that did not go leaves no mark
    and no event here: the caller says it. An answer for a slug that was removed from the
    queue goes to nobody.
    """
    number, slug = one.number, one.slug
    if one.answer is None or slug in run.removed:
        return Carried()
    form = (GO if one.answer.keeps else HELD) if one.holds else MESSAGE
    message = form.format(user=run.user.user, **asdict(one), **asdict(one.answer))
    thread = thread_of(run.home, slug)
    if not thread:
        return Carried(message)
    key = f"answer|{slug}|{number}"
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
    try:
        client.call("t3_thread_send", asked)
    except T3Error as error:
        return Carried(message, thread, error=str(error), refused=isinstance(error, T3Refused))
    _told(run.state, number, run.now.astimezone(UTC).isoformat(timespec="seconds"))
    line = f"{NOTE} {slug}: told its thread the answer to question {number}"
    run.find(slug, NOTE, line, message, key=f"answer {number}")
    return Carried(message, thread, told=True)


def tell(run: Pass, client: Client) -> None:
    """Send each answer that differs from its default, and each that keeps the default of a
    gate that holds, to the thread that asked, once (`carry`).

    An answer for a slug with no `Thread:` line to send to is said in a quiet event, once.
    One T3 Code refuses was carried to nobody, so it is a gate, once. Both are tried again
    on each pass until they go. An answer for a slug that was removed from the queue goes
    to nobody.
    """
    gone = run.removed
    for one in load(run.state):
        given = one.answer
        if given is None or given.closed_by != COMMAND or given.told:
            continue
        if given.keeps and not one.holds:
            continue
        if one.slug in gone:
            continue
        number, slug = one.number, one.slug
        went = carry(run, client, one)
        if went.told:
            run.say(f"{NOTE} {slug}: told its thread the answer to question {number}")
        elif not went.thread:
            line = f"{NOTE} {slug}: the answer to question {number} has no thread to go to"
            run.find(slug, NOTE, line, went.message, key=f"answer {number} no thread")
        elif went.refused:
            what = REFUSED.format(number=number)
            text = f"{went.error}\n\n{went.message}"
            run.gate(slug, what, text, key=f"answer {number} refused")
        else:
            error = went.error
            run.say(f"wait {slug}: the answer to question {number} could not be sent ({error})")


def _threads(client: Client, project_id: str) -> set[str]:
    """Every thread T3 Code lists for the project, settled or not."""
    found: set[str] = set()
    cursor = None
    for _ in range(20):
        asked = {"projectId": project_id, "limit": 100, **({"cursor": cursor} if cursor else {})}
        said = client.call("t3_thread_list", asked)
        found |= {thread["threadId"] for thread in said.get("threads", [])}
        cursor = said.get("nextCursor")
        if not cursor:
            break
    return found


def _proposed_at(run: Pass, number: int) -> None:
    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    with _locked(run.state):
        count, records = _kept(run.state)
        records = [replace(one, proposed=at) if one.number == number else one for one in records]
        _write(run.state, count, records)


def propose(run: Pass, client: Client) -> None:
    """Ask the thread of each open question that has no options to pipe its gate again with
    them, once for a question.

    A question has none when it was asked before a gate had to propose them. The message
    goes where an answer goes, to the thread on the `Thread:` line of the slug's brief or
    request. A slug with no such line, and a thread T3 Code no longer lists, get none: that
    is a quiet event, once, and the question stays open as it is. A list or a send that
    T3 Code did not answer is tried again on the next pass.

    That a question was asked is kept on its record (`proposed`), and not among the keys of
    what was sent: a snapshot forgets those for a slug whose pull request merged long ago,
    and the question may still be open then.
    """
    gone = run.removed
    owed = []
    for one in load(run.state):
        key = f"options|{one.slug}|{one.number}"
        if one.answer or one.options or one.proposed or one.slug in gone:
            continue
        thread = thread_of(run.home, one.slug)
        if thread:
            owed.append((one, key, thread))
        else:
            line = f"{NOTE} {one.slug}: question {one.number} has no options and no thread to ask"
            run.find(one.slug, NOTE, line, key=f"options {one.number} no thread")
    if not owed:
        return
    try:
        listed = _threads(client, run.project.project_id)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads to ask for options are not known ({error})")
        return
    for one, key, thread in owed:
        number, slug = one.number, one.slug
        if thread not in listed:
            line = f"{NOTE} {slug}: question {number} has no options, and its thread is gone"
            run.find(slug, NOTE, line, key=f"options {number} no thread listed")
            _proposed_at(run, number)
            continue
        message = PROPOSE.format(**asdict(one))
        client.recipients = client.recipients | {thread}
        asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
        try:
            client.call("t3_thread_send", asked)
        except T3Error as error:
            run.say(f"wait {slug}: its thread could not be asked for options ({error})")
            continue
        _proposed_at(run, number)
        line = f"{NOTE} {slug}: asked its thread for the options of question {number}"
        run.find(slug, NOTE, line, message, key=f"options {number}")
        run.say(line)


def _gate(args: argparse.Namespace, config: Config) -> int:
    """`jbus gate`: a thread's question for the user, kept as a record with a number.

    The same question from the same slug is the same record, so it is queued once, and one
    that was answered since is answered here. The event's text is the lines as they were
    sent: a home parks a gate from it.
    """
    project = verbs.here(config, args.project)
    run = Pass(config, project, datetime.now(UTC))
    text = sys.stdin.read().strip()
    if not text:
        raise Refused("refused: no lines on stdin")
    gone = queue.was_removed(run.state, args.slug)
    if gone:
        raise Refused(f"refused: {gone}, and a removed slug asks nothing")
    one, new = ask(run.state, run.home, args.slug, text, run.now)
    if one.answer:
        print(f"already answered: question {one.number}: {one.answer.line()}")
        return 0
    line = f"gate {args.slug}: question {one.number}: {one.question}"
    run.find(args.slug, "gate", line, text, key=one.key)
    print(f"queued: question {one.number}" if new else f"already sent: question {one.number}")
    return 0


def _answer(args: argparse.Namespace, config: Config) -> int:
    """`jbus answer`: close a question with the user's words, from wherever he answered."""
    project = verbs.here(config, args.project)
    heard = typed(args, config, "answer")
    closed = answer(
        config.state(project),
        args.number,
        heard.words if heard else " ".join(args.words),
        by=config.user.user if heard else args.by,
        at=heard.said_at if heard else args.at,
        where=str(Path.cwd()),
        keeps=args.keeps,
        user=config.user,
        heard=heard,
    )
    given = closed.answer
    if given.keeps and not closed.holds:
        carried = "nothing is sent"
    elif thread_of(config.home(project), closed.slug):
        carried = f"the next pass tells {closed.slug}'s thread"
    else:
        carried = f"{closed.slug} has no Thread: line in a brief or request, so no thread is told"
    print(f"answered: question {closed.number}: {given.line()}: {carried}")
    return 0


def _slug(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")


def _closes(closes: argparse.ArgumentParser) -> None:
    closes.add_argument("number", type=int, help="the question's number")
    closes.add_argument("--by", help="the user's name, with --at, for words that were typed")
    closes.add_argument(
        "--at",
        help='"<YYYY-MM-DD HH:MM ZONE>", the zone as jstack\'s config words it',
    )
    closes.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="the user's own message in T3 Code, in place of --by, --at and the words",
    )
    which = closes.add_mutually_exclusive_group(required=True)
    which.add_argument(
        "--default",
        dest="keeps",
        action="store_true",
        help="the answer is the default the thread took: nothing is sent to it, or a "
        "go-ahead for a gate that holds",
    )
    which.add_argument(
        "--differs",
        action="store_true",
        help="the answer is not the default, so the next pass tells the thread that asked",
    )
    closes.add_argument("words", nargs="*", help="the user's words, with --by and --at")


VERBS = (
    verbs.Verb("gate", "keep a question for the user, its lines on stdin", _slug, _gate),
    verbs.Verb("answer", "close a question with the user's answer", _closes, _answer, abbrev=False),
)

STEPS = (
    verbs.Step(
        "before-watch", 20, "questions.closed_in_files", lambda half: closed_in_files(half.run)
    ),
    verbs.Step("before-watch", 30, "questions.silent", lambda half: silent(half.run)),
    verbs.Step(
        "tellers",
        20,
        "questions.tell",
        lambda half: tell(half.run, half.client),
        ("sight", "client"),
    ),
    verbs.Step(
        "tellers",
        30,
        "questions.propose",
        lambda half: propose(half.run, half.client),
        ("sight", "client"),
    ),
)
