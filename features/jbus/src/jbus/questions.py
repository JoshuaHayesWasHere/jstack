"""A question for the user is one numbered record: `jbus gate` writes it, `jbus answer`
closes it, and a pass does either only as this module says (`park`, `silent`, `clear`).

`questions.json` in a project's state directory is `{"next", "records"}`. A record is a
`Question`:

- `number`: the record's own number, unique among the questions of the project and never used
  twice. `next` only grows. When a thread asks a question, jbus numbers it above every gate in
  the home's `gates.md` files at that moment. A home numbers its own gates without looking
  here, so a gate it makes later can have a question's number;
- `slug`: the brief or request that asked;
- `thread`: the thread that asked, at the time it asked, taken from the `Thread:` line of that
  brief or request, or from the gate's own `Asked by:` line where the brief has none yet;
- `question` and `default`: the one line the question asks, and what the thread did in place
  of an answer;
- `built_on` and `undo`: what the thread built on the default, and how to take it back;
- `context`: what the user needs to know to answer, from the gate's `Context:` line, or
  nothing;
- `options`: every option that the thread weighed, in the order of its `Option:` lines. Each is an
  `Option`: its short `name`, what `follows` from it, whether it is the `default` that the
  thread took, and whether it is the one the thread `recommended`. A record written before gates had
  options has none;
- `holds` and `fail_safe`: the case of `party.CASES` that the gate's `Holds:` line names, for a
  default that is irreversible or slow to revert, and the fail-safe that its `Fail-safe:` line
  names. Both are empty for a gate whose thread acted on its default at once, and for a record
  written before gates had them;
- `proposed`: for a question with no options, the time a pass asked its thread to pipe the
  options, or found that T3 Code no longer lists that thread. It is empty until a pass does
  either;
- `asked_at`: when `jbus gate` took the question;
- `answer`: empty while the question is open. Once it is closed, it is an `Answer`.
  `closed_by` is `jbus answer`, a home's `gates.md`, `silence`, or `cleared`. `words`, `by`
  and `at` are the user's words, who gave them and when. `where` is where the command ran,
  and `keeps` marks an answer that is the default. `told` is when jbus sent a differing answer
  to the asker. For an answer given as
  `--message`, `ref` is the `<thread id>/<message id>` that jbus read from T3 Code, `said_in` is
  that thread's title, and `checked` is true. For an answer typed with `--by` and `--at`,
  those three are empty and false. When a home closed the question in its file, the answer
  has the file's `Status:` line as its `words`, the file as `where`, and no `by` and no `at`,
  since jbus knows neither. When silence closed the question, the answer has the words
  `default`, `by` jbus, `at` the pass that closed it, `where` "settled at once", and
  `keeps`: it is not the user's word.

A gate is act-unless-stopped: the thread acts on its default at once, and the question is the
user's chance to stop it. A record stays open until `jbus answer` closes it, and it closes
once: `jbus answer` refuses a second answer and puts the first one in the refusal. A pass
also closes a record by silence, with its default, in the first pass that sees it (`QUIET` is
no time at all) when it has no `Holds:` line (`silent`), but for a go gate under the setting
`go = "silence"`, which waits its quiet window first. If the user answers after that, their
answer replaces the close by silence as the record's one answer, and jbus carries an answer
that differs as it carries any other.

A go gate is one whose default is `approve` (`queue.GO_DEFAULT`) and whose slug is a row of the
queue that waits for its go: a home's own pick for a new row, parked under the setting
`go = "silence"`. Nothing acts on its default until it closes, so it waits for an answer for the
setting's `go_quiet_minutes` and shows on the list of what waits on the user meanwhile. Its close
by silence approves the row where `queue.gone_ahead` lets it: basis `answer`, `closed_by`
`silence`. An answer of the user's closes it by `jbus answer`: one that keeps the default is the
user's go for the row and approves it under any setting, and one that differs approves nothing.

A pass raises a question of its own through the path a piped gate takes (`park`): the record, and
the `gate` event the Chef reads. `mainmoved` raises one when main's check starts no job. When the
cause passes, the pass closes such a question that still waits (`clear`), with `closed_by`
`cleared`, `by` jbus and words that say what passed. That close is not the user's word either, and
a question the user answered keeps the answer.

A gate whose default is irreversible or slow to revert holds: its thread does not act, and the
question waits for the user. Its `Holds:` line names the case, one of `party.CASES`, and its
`Fail-safe:` line names the dry-run, plan or bundle on which the user answers. Silence never closes
such a gate. `jbus gate` refuses a `Holds:` line with no filled `Fail-safe:` line, an unknown
case, two `Holds:` lines, and a `Fail-safe:` line with no `Holds:` line.

`jbus gate` refuses lines that are not one filled-in gate of
`features/home/templates/gates.md`, and says `not sent` and what they lack (`_shaped`). It
refuses a first line that is not `## Gate <n>: ` with the question (or `## Gate <number>: `
for a gate that a home's `gates.md` numbered), more than one `## ` line, a missing
`Status: open` line, and a line of the template's head that is missing or still holds its
placeholder. jbus reads the labels from the template, the one copy, so a skill pipes the gate
and checks none of this itself.

While homes still keep a `gates.md`, a pass also closes a record when it finds the same gate
in such a file with `Status: answered` (`closed_in_files`), because that home took the
answer and carried it to the thread itself. It never closes a gate that holds that way: only
the user's own answer closes one.

Every verb that would write the file refuses a file that does not parse, or one that holds
something that is not a record (`Unparsable`). If a verb wrote such a file back, it would lose
the questions and hand their numbers out again. A pass raises a gate about the file, keeps
the questions its list had, and reports no answered gate until it can read the file.

When the same slug asks the same question again, it is the same record (`mirror.gate_key`), open or
closed. If the record is still open, jbus replaces its default, undo and built-on lines, its context
and its options with the new ones, because a thread parks the same gate again at a later head.

A gate proposes two options or more: one of them is the default that the thread took, and it is the
one the thread recommends (`_proposed`). `jbus gate` refuses a gate that breaks this rule, and says
`not sent` with the whole form of an `Option:` line, so a thread whose skill is older than options
can mend its lines from the refusal alone. A question that is open with no options was asked before
that rule. A pass asks its thread, once, to pipe the same gate again with options (`propose`). It
asks the thread on the `Thread:` line of the slug's brief or request, and nobody where there is no
such line or T3 Code no longer lists the thread.

jbus sends nothing for an answer that keeps the default, except for a gate that holds: its thread
waits, so jbus carries that answer as a go-ahead (`GO`). jbus carries an answer that differs
(`carry`) as one queued message to the thread on the `Thread:` line of the slug's brief or request,
with the words and the undo line, under the retry key `answer|<slug>|<number>`. The message is a
`note`, a quiet event, so no answer starts a POST. The view sends an answer given on its page at
once, and the pass sends every answer that jbus has not sent yet (`tell`). When T3 Code refuses an
answer, the answer was not carried: jbus raises a `gate` about it, once, and the pass sends the
answer again until it goes. `thread` records who asked, and jbus never sends to it: jbus sends only
to a thread that a brief or a request names (`t3`).
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import below, skills
from jbriefs.home import thread_of
from jbus import END_TURN, Config, Refused, locked, mirror, outbox, queue, t3, verbs, write_json
from jbus.party import CASES, Evidence, Party
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused

LOCK = "questions.lock"
EVENTS = {"note": "quiet"}
NAME = "questions.json"
SOURCE = "jbus"
NOTE = "note"
TEMPLATE = "gates.md"
_HEAD = re.compile(r"## Gate (<n>|[0-9]+): [^<]")
GO = (
    "jbus: {user} answered question {number} ({question}) with the default ({default}), which "
    'held for the answer ({holds}). The words, {at}: "{words}". Fail-safe: {fail_safe}. Go '
    "ahead with the default now, and add one line to the last Result or Report saying what "
    "you did. " + END_TURN
)
HELD = (
    "jbus: {user} answered question {number} ({question}), which held for the answer "
    '({holds}), and the answer is not the default ({default}). The words, {at}: "{words}". Do '
    "not take the default: do what the answer says, and add one line to the last Result or "
    "Report saying what you did. " + END_TURN
)
MESSAGE = (
    "jbus: {user} answered question {number} ({question}), and the answer is not the default "
    'you took ({default}). The words, {at}: "{words}". Undo: {undo}. Built on the default: '
    "{built_on}. Take the default back, do what the answer says, and add one line to the last "
    "Result or Report saying what you changed. " + END_TURN
)
_THREAD = re.compile(r"\bthread (\S+)")
_GROUP = re.compile(r"\([^()]*\)$")
COMMAND, HOME, SILENCE, CLEARED = "jbus answer", "gates.md", "silence", "cleared"
QUIET = timedelta(0)
UNANSWERED = "settled at once"
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
    "the user needs to know to answer, with the links to it>`. And "
    + FORM
    + ". "
    + END_TURN
    + "\n\n"
    "## Gate <n>: {question}\nStatus: open\nAsked by: {slug}, thread {thread}\n"
    "Default: {default}\nBuilt on it: {built_on}\nUndo: {undo}"
)


class Unparsable(Refused):
    """`questions.json` holds something this module did not write, so no verb writes over
    it."""


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
        if self.closed_by == CLEARED:
            return f"closed by {self.by}, {self.at}, since its cause passed: {self.words}"
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
        """Return the key that names the question, whether the question arrived piped or was
        read from a file."""
        return mirror.gate_key(self.slug, self.question)


def path(state: Path) -> Path:
    return state / NAME


def _kept(state: Path) -> tuple[int, list[Question]]:
    """Return the counter and every record. A missing file means no record. For any other
    file that this module did not write, raise `Unparsable`."""
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
    """Return every record, open or closed, by number, or none where the file does not parse.
    It takes no lock and writes nothing."""
    try:
        return read(state)
    except Unparsable:
        return []


def read(state: Path) -> list[Question]:
    """Return every record, as `load` gives them, or raise `Unparsable` for a file that this
    module did not write."""
    return _kept(state)[1]


def _floor(home: Path) -> int:
    """Return one more than the highest gate number in the home's `gates.md` or in a scoped
    home's `gates.md`."""
    numbers = (number for _, number, *_ in mirror.home_gates(home) if number.isdigit())
    return max([0, *map(int, numbers)]) + 1


def _count(number: int, noun: str) -> str:
    words = ("no", "one", "two", "three")
    return f"{words[number] if number < len(words) else number} {noun}{'' if number == 1 else 's'}"


def _proposed(lines: str) -> tuple[Option, ...]:
    """Return the options of a gate's lines, or `Refused` with what they lack.

    The user picks among the options that the thread weighed, so a gate has two options or more,
    each under a name of its own. One of them is the default that the thread took, and at most one
    is the thread's pick. A mark such as `(default)` goes in parentheses after the name. A name
    that ends in parentheses holds a mark that the thread did not spell as one, and if jbus kept
    it as a name, the option would have no mark. The default that the thread took is the one it
    recommends, because a pass may close the question by silence, with that default.
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
    """Return the case that a gate's `Holds:` line names and the fail-safe that its
    `Fail-safe:` line names, or `Refused` with what is wrong with those lines. For a gate that
    acts at once, both are empty."""
    said = {
        name: [
            line[len(name) + 1 :].strip()
            for line in lines.splitlines()
            if line.startswith(f"{name}:")
        ]
        for name in ("Holds", "Fail-safe")
    }
    holds, safe = said["Holds"], said["Fail-safe"]
    cases = " | ".join(CASES)
    if len(holds) > 1 or len(safe) > 1:
        what = f"the gate has two {'Holds' if len(holds) > 1 else 'Fail-safe'}: lines"
    elif holds and holds[0] not in CASES:
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


def _labels() -> list[str]:
    """Return the labels of the template's head: the lines under its first line, down to the
    first blank line."""
    head = itertools.takewhile(
        str.strip, skills.where("template", TEMPLATE).read_text().splitlines()[1:]
    )
    return [line.split(":", 1)[0] + ":" for line in head if ":" in line]


def _filled(said: str) -> bool:
    """Return whether a label's text, as `jbriefs.below.line` reads it, is more than its
    placeholder."""
    return bool(said.strip()) and not said.strip().startswith("<")


def _shaped(lines: str) -> None:
    """Raise `Refused`, with what is wrong, for lines that are not one filled-in gate of the
    template, and return None for lines that are."""
    rows = lines.splitlines()
    if not rows or not _HEAD.match(rows[0]):
        what = "the first line is not '## Gate <n>: ' and the question"
    elif sum(row.startswith("## ") for row in rows) != 1:
        what = "it is not one gate"
    elif "Status: open" not in rows:
        what = "the gate has no Status: open line"
    else:
        bare = [
            label
            for label in _labels()
            if not any(
                row.startswith(f"{label} ") and _filled(row[len(label) + 1 :]) for row in rows
            )
        ]
        if not bare:
            return
        what = f"the gate has no {bare[0]} line that is filled in"
    raise Refused(f"not sent: {what}.")


def ask(state: Path, home: Path, slug: str, lines: str, now: datetime) -> tuple[Question, bool]:
    """Store the gate that a thread piped, and return its record and whether the record is new.

    `ask` refuses lines that are not one filled-in gate of the template (`_shaped`). Lines
    with no `Default:` line come from a thread that waits, and no record would say what an
    answer undoes. It also refuses lines that do not propose two options, one of them the
    default and the recommended one (`_proposed`), and lines with a wrong `Holds:` line
    (`_held`).
    """
    _shaped(lines)
    asked, default = mirror.question(lines), below.line(lines, "Default:")
    options = _proposed(lines)
    holds, fail_safe = _held(lines)
    named = _THREAD.search(below.line(lines, "Asked by:"))
    with locked(state, LOCK):
        count, records = _kept(state)
        key = mirror.gate_key(slug, asked)
        said = {
            "thread": thread_of(home, slug) or (named[1] if named else ""),
            "default": default,
            "built_on": below.line(lines, "Built on it:"),
            "undo": below.line(lines, "Undo:"),
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
        at = jsettings.stamp(now)
        made = Question(number=number, slug=slug, question=asked, asked_at=at, **said)
        _write(state, number + 1, [*records, made])
    return made, True


def park(run: Pass, slug: str, lines: str) -> tuple[Question, bool]:
    """Keep a gate as a question (`ask`), and queue its `gate` event while it waits for an
    answer. It is the one path a gate takes, piped by a thread to `jbus gate` or raised by a
    pass."""
    one, new = ask(run.state, run.home, slug, lines, run.now)
    if not one.answer:
        line = f"gate {slug}: question {one.number}: {one.question}"
        run.find(slug, "gate", line, lines, key=one.key)
    return one, new


def clear(run: Pass, number: int, words: str) -> None:
    """Close a question that waits for an answer (`_open`) because what it asked about has
    passed, and say so in `words`. A question the user answered keeps that answer. jbus sends
    nothing, and writes one quiet `note` event."""
    at = jsettings.stamp(run.now)
    given = Answer(words, SOURCE, at, "a jbus pass", True, closed_by=CLEARED)
    with locked(run.state, LOCK):
        count, records = _kept(run.state)
        found = [one for one in records if one.number == number and _open(one)]
        if not found:
            return
        _write(
            run.state,
            count,
            [replace(one, answer=given) if one in found else one for one in records],
        )
    line = f"{NOTE} {found[0].slug}: question {number} closed, {words}"
    run.find(found[0].slug, NOTE, line, key=f"cleared {number}")
    run.say(line)


def answer(
    state: Path,
    number: int,
    *,
    party: Party,
    evidence: Evidence,
    where: str,
    keeps: bool,
    user: jsettings.Settings,
) -> tuple[Question, str]:
    """Close a question with the user's answer, as `party` carried it on `evidence`: its words,
    their time and where jbus read them, and return it with the line of what the answer started.
    `answer` refuses a second answer and puts the first in the refusal. The one exception is a
    question that a pass closed by silence: that close is not the user's answer, so the user's
    answer replaces it. Whether the party may answer a gate that holds, or a go gate for a brief
    that holds, is `jbus.acts`'s to say, before it calls this.

    An answer that keeps the default of a go gate is the user's go for its row: the row is
    approved on it (`queue.gone_ahead`), and the line says so.

    `keeps` says the answer is the default. Only the person who heard the answer knows
    whether it keeps the default, because words such as "yes" do not say it.
    """
    words = " ".join(evidence.words.split())
    if not words:
        raise Refused("refused: an answer has the user's words")
    with locked(state, LOCK):
        count, records = _kept(state)
        found = [one for one in records if one.number == number]
        if not found:
            numbers = ", ".join(str(one.number) for one in records if one.answer is None)
            raise Refused(f"refused: no question {number}, open: {numbers or 'none'}")
        (one,) = found
        if one.answer and one.answer.closed_by != SILENCE:
            raise Refused(f"refused: question {number} was answered already: {one.answer.line()}")
        by = "the bot" if party.kind == "bot" else user.user
        given = Answer(words, by, evidence.said_at, where, keeps)
        if evidence.checked or evidence.ref:
            given = replace(
                given, ref=evidence.ref, said_in=evidence.said_in, checked=evidence.checked
            )
        closed = replace(one, answer=given)
        _write(state, count, [closed if each.number == number else each for each in records])
    if not (keeps and go_gate(closed)):
        return closed, ""
    said = queue.Said(given.words, given.at, given.said_in, given.checked, given.ref)
    return closed, queue.gone_ahead(state, closed.slug, number, given.at, user, said)


def question(state: Path, number: int) -> Question | None:
    """The question of that number, as the file has it now."""
    return next((one for one in read(state) if one.number == number), None)


def basis(state: Path, ref: str) -> queue.Said:
    """Return the answer that closed the question of that number, as the basis of an
    approval.

    A question that is open, or one that a home closed in its own file, has no words from the
    user with a time, so `basis` refuses it.
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
    with locked(state, LOCK):
        count, records = _kept(state)
        records = [
            replace(one, answer=replace(one.answer, told=how))
            if one.number == number and one.answer
            else one
            for one in records
        ]
        _write(state, count, records)


def closed_in_files(run: Pass) -> None:
    """Close each open question when a `gates.md` of the home marks its gate as answered.

    Until the skills read jbus, a home that takes an answer in its own thread writes the
    answer in its `gates.md` and sends the answer to the thread itself. So this function
    closes the record with the words of that `Status:` line, and jbus sends nothing. Those
    words replace a close by silence. A gate that holds waits for the user's own answer, so
    the file never closes it: the pass says so once, with a quiet `note`, and leaves it open.
    """
    answered = {
        key: (below.line(body, "Status:"), file)
        for file, _, _, body, key in mirror.home_gates(run.home)
        if below.line(body, "Status:").startswith("answered")
    }
    if not answered or not any(_open(one) for one in load(run.state)):
        return
    with locked(run.state, LOCK):
        count, records = _kept(run.state)
        closed, held = [], []
        for one in records:
            if _open(one) and one.key in answered and one.holds:
                held.append((one, answered[one.key][1]))
            elif _open(one) and one.key in answered:
                status, file = answered[one.key]
                given = Answer(status, "", "", str(file), False, closed_by=HOME)
                one = replace(one, answer=given)
            closed.append(one)
        if closed != records:
            _write(run.state, count, closed)
    for one, file in held:
        line = (
            f"{NOTE} {one.slug}: question {one.number} holds ({one.holds}) for "
            f"{run.user.user}'s own answer, and {file} marked it answered: it stays open"
        )
        if run.find(one.slug, NOTE, line, key=f"held {one.number}"):
            run.say(line)


def _open(one: Question) -> bool:
    """Return whether a record waits for an answer: it is open, or closed by silence alone."""
    return one.answer is None or one.answer.closed_by == SILENCE


def silent(run: Pass) -> None:
    """Close by silence, with its default, each open question that has no `Holds:` line, in the
    first pass that sees it (`QUIET` is no time at all), or, for a go gate under the setting
    `go = "silence"`, once its quiet window (`go_quiet_minutes`) has passed. The thread acted on
    the default when it asked the question, so jbus sends nothing. jbus writes one quiet `note`
    event for each question it closes."""
    if not path(run.state).exists():
        return
    at = jsettings.stamp(run.now)
    given = Answer("default", SOURCE, at, UNANSWERED, True, closed_by=SILENCE)
    window = timedelta(minutes=run.user.go_quiet_minutes)
    with locked(run.state, LOCK):
        try:
            count, records = _kept(run.state)
        except Unparsable:
            return
        silence = run.user.go == jsettings.SILENCE
        goes = _go_gates(run.state) if silence and any(map(go_gate, records)) else set()
        closed = [
            replace(one, answer=given)
            if _quiet(one, run.now, window if one.slug in goes and go_gate(one) else QUIET)
            else one
            for one in records
        ]
        if closed == records:
            return
        _write(run.state, count, closed)
    for was, one in zip(records, closed, strict=True):
        if was is not one:
            line = f"{NOTE} {one.slug}: question {one.number} closed with its default, {UNANSWERED}"
            run.find(one.slug, NOTE, line, key=f"silence {one.number}")
            run.say(line)
            if one.slug in goes and go_gate(one):
                went = queue.gone_ahead(
                    run.state, one.slug, one.number, run.user.stamp(run.now), run.user, None
                )
                if went:
                    run.say(f"queue {run.project.name}: {went}")


def go_gate(one: Question) -> bool:
    """Return whether the question's default is to approve its row: a go gate."""
    return one.default.strip().lower() == queue.GO_DEFAULT


def _go_gates(state: Path) -> set[str]:
    """Return the slugs of the rows that wait for a go: a gate on one with the default `approve`
    is a go gate."""
    try:
        rows = queue.load(state)
    except queue.Unparsable:
        return set()
    return {
        row["slug"]
        for row in rows
        if row.get("status", "queued") == "queued" and not row.get("approved")
    }


def _quiet(one: Question, now: datetime, window: timedelta = QUIET) -> bool:
    """Return whether silence closes the question now. A gate that holds waits for the user, so
    silence never closes it."""
    if one.answer or one.holds:
        return False
    try:
        asked = datetime.fromisoformat(one.asked_at)
    except ValueError:
        return False
    return asked.tzinfo is not None and now - asked >= window


def waits(state: Path, user: jsettings.Settings) -> Callable[[Question], str]:
    """Return what says, of a go gate, why its close by silence starts nothing: the setting `go`
    is not `silence`, or silence starts no row of its brief (`queue.unsilenced`). It says nothing
    of any other question, or of a go gate whose silence starts its row."""

    def why(one: Question) -> str:
        if not go_gate(one):
            return ""
        if user.go != jsettings.SILENCE:
            return f"the setting go is {user.go}, not {jsettings.SILENCE}"
        text = queue.brief(state, one.slug)
        return queue.unsilenced(text) if text is not None else ""

    return why


def _state(one: Question, why: str) -> str:
    """Return the words that the line of a waiting question adds: that its default holds
    until the user answers, with the fail-safe, or that the thread already acted on the
    default. A go gate's line says that silence starts its row, or `why` it starts nothing."""
    if one.holds:
        return f" It holds ({one.holds}) for your answer, with its fail-safe: {one.fail_safe}."
    if go_gate(one) and why:
        return f" It waits for your answer, since silence starts nothing where {why}."
    if go_gate(one):
        return f" Unless you answer, it starts {one.slug} when its quiet window ends."
    return " Its default is acted on already, and stands unless you stop it."


def item(one: Question, why: str = "") -> dict[str, Any]:
    """Return an open question as a gate item for the list of what waits on the user. The
    item has `acted` where the thread acted on the default at once, and the case and the
    fail-safe of a gate that holds. `why` is what `waits` says of it. No go gate is `acted`: its
    default waits for its close."""
    return {
        "kind": "gate",
        "key": f"gate:q{one.number}",
        "source": SOURCE,
        "line": f"question {one.number}: {one.question}{_state(one, why)}",
        "number": str(one.number),
        "question": one.question,
        "default": one.default,
        "home": "",
        "slug": one.slug,
        "since": one.asked_at,
        "acted": not one.holds and not go_gate(one),
        "holds": one.holds,
        "fail_safe": one.fail_safe,
    }


def listed(item: dict[str, Any]) -> bool:
    """Return whether an item on the list of what waits on the user is a question from this
    file."""
    return item.get("source") == SOURCE


@dataclass(frozen=True)
class Carried:
    """A Carried says how the send of one answer to its asker went. `told` says the answer went,
    and `thread` is the thread that should get the answer, if it had one. `error` is what T3 Code
    said when it did not take the answer, and `refused` says that T3 Code answered and refused
    the answer. `held` says the outbox holds the answer until the cap on the thread's instance
    resets."""

    message: str = ""
    thread: str = ""
    told: bool = False
    error: str = ""
    refused: bool = False
    held: bool = False


def carry(run: Pass, client: Client, one: Question) -> Carried:
    """Send one answer to the thread that asked the question. The answer either differs from
    the default, or keeps the default of a gate that holds. The thread waits for that answer:
    it is the go-ahead (`GO`) or, when the answer differs, the instruction not to take the
    default (`HELD`).

    The answer goes as one queued message to the thread on the `Thread:` line of the slug's brief or
    request, under the retry key `answer|<slug>|<number>`. The pass and the view both send answers
    through this function, so neither of them sends an answer a second time. When the answer goes,
    this function marks its record `told` and writes a quiet event. When the answer does not go,
    this function writes no mark and no event, and the caller reports the failure. An answer for a
    slug that was removed from the queue goes to nobody.
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
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=slug,
            key=key,
            text=message,
            template="answer",
            needs="act",
        )
    except T3Error as error:
        return Carried(message, thread, error=str(error), refused=isinstance(error, T3Refused))
    if not went:
        return Carried(message, thread, held=True)
    _told(run.state, number, jsettings.stamp(run.now))
    line = f"{NOTE} {slug}: told its thread the answer to question {number}"
    run.find(slug, NOTE, line, message, key=f"answer {number}")
    return Carried(message, thread, told=True)


def tell(run: Pass, client: Client) -> None:
    """Send each answer that differs from its default, and each answer that keeps the default
    of a gate that holds, once to the thread that asked (`carry`).

    When the slug has no `Thread:` line, jbus writes a quiet event about the answer, once. When T3
    Code refuses an answer, the answer reached nobody, so jbus raises a gate about it, once. jbus
    tries both kinds of answer again on each pass until they go. An answer for a slug that was
    removed from the queue goes to nobody.
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
        elif went.held:
            continue
        elif went.refused:
            what = REFUSED.format(number=number)
            text = f"{went.error}\n\n{went.message}"
            run.gate(slug, what, text, key=f"answer {number} refused")
        else:
            error = went.error
            run.say(f"wait {slug}: the answer to question {number} could not be sent ({error})")


def _threads(client: Client, project_id: str) -> set[str]:
    """Return every thread T3 Code lists for the project, settled or not."""
    return {thread["threadId"] for thread in t3.listed(client, project_id)}


def _proposed_at(run: Pass, number: int) -> None:
    at = jsettings.stamp(run.now)
    with locked(run.state, LOCK):
        count, records = _kept(run.state)
        records = [replace(one, proposed=at) if one.number == number else one for one in records]
        _write(run.state, count, records)


def propose(run: Pass, client: Client) -> None:
    """For each open question with no options, ask its thread once to pipe the gate again,
    with options.

    A question has no options when a thread asked it before gates had to propose options. The
    message goes where an answer goes, to the thread on the `Thread:` line of the slug's brief or
    request. jbus sends no message for a slug with no such line, or to a thread that T3 Code no
    longer lists. It writes a quiet event instead, once, and the question stays open as it is. When
    T3 Code did not answer a list or a send, jbus tries the list or the send again on the next pass.

    jbus records in the question's record (`proposed`) that it asked the thread. It does not record
    this among the keys of what it sent, because a snapshot drops those keys for a slug whose
    pull request merged long ago, while the question may still be open.
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
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=slug,
                key=key,
                text=message,
                template="options",
                needs="act",
            )
        except T3Error as error:
            run.say(f"wait {slug}: its thread could not be asked for options ({error})")
            continue
        if not went:
            continue
        _proposed_at(run, number)
        line = f"{NOTE} {slug}: asked its thread for the options of question {number}"
        run.find(slug, NOTE, line, message, key=f"options {number}")
        run.say(line)


def _gate(args: argparse.Namespace, config: Config) -> int:
    """`jbus gate`: keep a thread's question for the user as a record with a number.

    The same question from the same slug is the same record, so jbus queues it once. If the
    user has answered it since, `jbus gate` prints that answer. The event's text is the lines
    as the thread sent them, and a home parks a gate from that text.
    """
    project = verbs.here(config, args.project)
    run = Pass(config, project, datetime.now(UTC))
    text = verbs.piped("gate", "the gate's lines").strip()
    if not text:
        raise Refused("refused: no lines on stdin")
    gone = queue.was_removed(run.state, args.slug)
    if gone:
        raise Refused(f"refused: {gone}, and a removed slug asks nothing")
    one, new = park(run, args.slug, text)
    if one.answer:
        print(f"already answered: question {one.number}: {one.answer.line()}")
        return 0
    print(f"queued: question {one.number}" if new else f"already sent: question {one.number}")
    return 0


def _slug(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")


def closes(closes: argparse.ArgumentParser) -> None:
    """Add the arguments of `jbus answer`, whose verb `jbus.acts` declares."""
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


VERBS = (verbs.Verb("gate", "keep a question for the user, its lines on stdin", _slug, _gate),)

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
