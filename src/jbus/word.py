"""The user's word, down to a home: one record, written by `jbus word` and sent by jbus.

It is for an approval or an instruction that answers no open question, said where the user
was, which is most often to Sous Chef. `words.json` in a project's state directory is a list
of `Word`:

- `id`: the first 12 of a hash of the project, the words, `by` and `at`, and of `ref` where
  there is one, so the same word for the same project is the same record however often the
  command is run;
- `words`, `by`, `at`: what the user said, and who and when;
- `ref`, `said_in`, `checked`: for a word given as `--message`, the `<thread id>/<message
  id>` jbus read from T3 Code, that thread's title, and true: the words and the time are the
  message's own. A word typed with `--by` and `--at` has no `ref`, no `said_in`, and
  `checked` false;
- `kept_at`: when `jbus word` took it;
- `thread` and `sent_at`: the home's thread it went to, and when. Both are empty while it
  waits;
- `skipped`: why it was posted to nobody, for a word recorded from or by the home it is for:
  `thread` is then that home's thread and `sent_at` the time it was kept, so the word is
  done, and the home is not told what it recorded itself. It is empty for every other word;
- `waits`: why it has not gone yet, as the log last said it.

A word goes once, as one queued message to the thread in the home's `home-id`, which is
read when it is sent and not when it is kept (`home`). The command sends it at once, except
to the home that recorded it: a word said in that home's own thread (`--message` whose
thread is the home's) or recorded by it (`--from <thread id>`) is kept as sent, with
`skipped` saying why, and with `--all` only that project's copy is. A home that handed off
and has no `home-id` is nobody, so such a word waits for the next home as any other. One
that could not go waits in the file, and each pass tries it again (`deliver`): a home with
no `home-id`, or one that handed off, gets it on the pass after the next home's start wrote
its id there. The retry key is `word|<project>|<id>|<thread>`, and `sent_at` is written
only after T3 Code said yes.

Nothing of a word is an event. It is in no outbox, so no POST to a project's webhook or to
the top-level one carries it, and whoever ran the command hears nothing back. The log has a
line for it all the same (`wake.Box.record`), which `jbus events` prints: the words, `by`,
`at`, and `to`, the thread it went to or nothing while it waits or was posted to nobody. A
word T3 Code refuses is such a line too, and waits like any other.

The command holds no lock of the pass, so a pass and the command can hold the same unsent
word. What became of one is written to the record as it is in the file then, under
`words.lock`, and a word that has `sent_at` is never changed again (`_change`).

A file that does not parse, or holds a record that is not one, is `Unparsable`: nothing
writes over it, and a pass says so in a gate and goes on.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import jsettings
from jbus import Config, Refused, queue, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused, typed
from jbus.wake import Pass

if TYPE_CHECKING:
    from jbus.cli import Half

NAME = "words.json"
KIND = "word"
MESSAGE = (
    "jbus: this is {by}'s own word, said {at} and carried to this home by jbus. Take it as "
    "said by {by} in this thread. It answers no open question, and nothing is sent back "
    "for it. It is word {id}: a row it approves is approved with --word {id}.\n\n{words}"
)
NO_HOME = "its home has no home-id, so it goes on the pass after that home's next start"
NO_T3 = "jbus is not signed in to T3 Code"
NO_ANSWER = "T3 Code gave no answer"
REFUSED = "T3 Code refused it"
SAID_IN_HOME = "it was said in this project's own home thread {thread}"
BY_HOME = "it was recorded by this project's home thread {thread}"
_WAS = re.compile(r"^Was home:[ \t]*(\S+)", re.MULTILINE)


class Unparsable(Refused):
    """`words.json` is not what this module writes, so nothing is written over it."""


@dataclass(frozen=True)
class Word:
    id: str
    words: str
    by: str
    at: str
    kept_at: str
    thread: str = ""
    sent_at: str = ""
    waits: str = ""
    ref: str = ""
    said_in: str = ""
    checked: bool = False
    skipped: str = ""


def path(state: Path) -> Path:
    return state / NAME


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "words.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load(state: Path) -> list[Word]:
    """Every word of the project, oldest first. It takes no lock and writes nothing."""
    file = path(state)
    if not file.exists():
        return []
    try:
        return [Word(**one) for one in json.loads(file.read_text())]
    except (OSError, ValueError, TypeError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error


def _write(state: Path, words: list[Word]) -> None:
    write_json(path(state), [asdict(one) for one in words], mode=0o600)


def said(words: str, by: str, at: str, user: jsettings.Settings) -> str:
    """The words as they are kept, on one line. What is not the user's word is refused."""
    if by != user.user:
        raise Refused(f"refused: only {user.user} gives a word, not {by}")
    if not user.takes(at):
        raise Refused(f'refused: --at is "{user.form(at)}"')
    words = " ".join(words.split())
    if not words:
        raise Refused("refused: a word has the user's words")
    return words


def keep(
    run: Pass,
    words: str,
    by: str,
    at: str,
    heard: queue.Said | None = None,
    recorder: str = "",
) -> Word:
    """Keep a word for the project. The answer is its record: the one there was, or a new one.

    `heard` is the message jbus read the words and the time from, for a word given as
    `--message`: `ref` is then its `<thread id>/<message id>`. `recorder` is the thread that
    ran `jbus word`, for `--from`. A new word said in the project's home thread, or recorded
    by it, is kept as sent to that thread and posted to nobody (`skipped`).
    """
    ref = heard.ref if heard else ""
    named = json.dumps([run.project.name, words, by, at, *([ref] if ref else [])])
    name = hashlib.sha256(named.encode()).hexdigest()[:12]
    with _locked(run.state):
        kept = load(run.state)
        for one in kept:
            if one.id == name:
                return one
        kept_at = run.now.astimezone(UTC).isoformat(timespec="seconds")
        made = Word(name, words, by, at, kept_at)
        if heard:
            made = replace(made, ref=ref, said_in=heard.said_in, checked=heard.checked)
        mine = home(run.home)
        if mine and mine == ref.partition("/")[0]:
            made = replace(
                made, thread=mine, sent_at=kept_at, skipped=SAID_IN_HOME.format(thread=mine)
            )
        elif mine and mine == recorder:
            made = replace(made, thread=mine, sent_at=kept_at, skipped=BY_HOME.format(thread=mine))
        _write(run.state, [*kept, made])
    if made.skipped:
        about = {"words": words, "by": by, "at": at, "to": ""}
        run.box.record(KIND, f"{KIND} {run.project.name}: kept, {made.skipped}", words, word=about)
    return made


def basis(state: Path, name: str) -> queue.Said:
    """The word with that id, as what an approval rests on. One the file has not is refused."""
    for one in load(state):
        if one.id == name:
            return queue.Said(one.words, one.at, one.said_in, one.checked, one.ref)
    raise Refused(f"refused: {path(state)} has no word {name}")


def home(directory: Path) -> str:
    """The thread of the project's home now: the first word of its `home-id`, or nothing.

    A home that handed off is nobody until the next one's start writes its own id there: the
    id on the `Was home:` line of `handoff.md` counts as none, as it does for a crewmate.
    """

    def read(name: str) -> str:
        try:
            return (directory / name).read_text(errors="replace")
        except OSError:
            return ""

    now = (read("home-id").split()[:1] or [""])[0]
    was = _WAS.search(read("handoff.md"))
    return "" if was and was[1] == now else now


def _change(run: Pass, one: Word, **changed: str) -> bool:
    """Write what became of a word, and add the line of it to the log. The answer is whether
    it was written: a word that was sent since `one` was read is left as it is."""
    with _locked(run.state):
        kept = load(run.state)
        found = [each for each in kept if each.id == one.id and not each.sent_at]
        if not found:
            return False
        now = replace(found[0], **changed)
        _write(run.state, [now if each.id == one.id else each for each in kept])
    how = f"sent to {now.thread}" if now.sent_at else f"waits, {now.waits}"
    about = {"words": now.words, "by": now.by, "at": now.at, "to": now.thread}
    run.box.record(KIND, f"{KIND} {run.project.name}: {how}", now.words, word=about)
    return True


def post(client: Client | None, thread: str, message: str, key: str) -> str:
    """Send one queued message to a home's thread, under the retry key `key`, so a second
    send of the same key is the first. The answer is why it did not go, or nothing where T3
    Code took it. `jbus.item` sends a steer's message through here too."""
    if not thread or client is None:
        return NO_T3 if thread else NO_HOME
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
    try:
        client.call("t3_thread_send", asked)
    except T3Refused:
        return REFUSED
    except T3Error:
        return NO_ANSWER
    return ""


def deliver(run: Pass, client: Client | None) -> None:
    """Send each word that waits to the home's thread, once. One that cannot go waits on.

    Why it waits is written once, and again when the reason changes.
    """
    for one in load(run.state):
        if one.sent_at:
            continue
        thread, name = home(run.home), run.project.name
        key = f"{KIND}|{name}|{one.id}|{thread}"
        waits = post(client, thread, MESSAGE.format(**asdict(one)), key)
        if not waits:
            at = run.now.astimezone(UTC).isoformat(timespec="seconds")
            if _change(run, one, thread=thread, sent_at=at, waits=""):
                run.say(f"{KIND} {name}: sent to {thread}")
            continue
        if waits != one.waits and _change(run, one, waits=waits):
            run.say(f"wait {name}: a word of {one.at} {waits}")


def line(run: Pass, was: Word) -> str:
    """What `jbus word` prints for one project: how the word it kept as `was` stands now."""
    (one,) = [one for one in load(run.state) if one.id == was.id]
    name = run.project.name
    if one.skipped:
        return f"kept: {name}, not posted, {one.skipped}, word {one.id}"
    if one.sent_at:
        how = "already sent" if was.sent_at else "sent"
        return f"{how}: {name}, to {one.thread}, word {one.id}"
    return f"waits: {name}, {one.waits}, word {one.id}"


def _word(args: argparse.Namespace, config: Config) -> int:
    """`jbus word`: the user's word for one project's home or for every one, from any checkout.

    It is kept, and sent at once to the thread in the home's `home-id`. The same words, `by`
    and `at` for the same project are the same word: a second run sends nothing again. The
    words are typed with `--by` and `--at`, or are those of the message `--message` names,
    which jbus reads from T3 Code with its time. A word said in a project's home thread, or
    recorded by it (`--from`), is kept there as sent and posted to nobody (`keep`).
    `--to` names a project or a scratch home (`jbus.Scratch`), and `--all` is every project:
    a scratch home is for no word about the repos.
    A project that refuses, as one whose `words.json` does not parse, is said and passed
    over: the others still get it, and the answer is then 1.
    """
    projects = config.projects if args.all else (config.addressee(args.to),)
    heard = typed(args, config, "word")
    by, at = (config.user.user, heard.said_at) if heard else (args.by, args.at)
    words = said(heard.words if heard else " ".join(args.words), by, at, config.user)
    try:
        client = Client(config.server, config.token_path)
    except Refused:
        client = None
    now = datetime.now(UTC)
    code = 0
    for project in projects:
        run = Pass(config, project, now, lambda _: None)
        try:
            was = keep(run, words, by, at, heard, args.recorder or "")
            deliver(run, client)
            print(line(run, was))
        except Refused as error:
            print(error)
            code = 1
    return code


def _down(down: argparse.ArgumentParser) -> None:
    homes = down.add_mutually_exclusive_group(required=True)
    homes.add_argument(
        "--to", metavar="PROJECT", help="the project or the scratch home whose home it is for"
    )
    homes.add_argument("--all", action="store_true", help="the home of every project")
    down.add_argument("--by", help="the user's name, with --at, for words that were typed")
    down.add_argument(
        "--at",
        help='"<YYYY-MM-DD HH:MM ZONE>", the zone as jstack\'s config words it',
    )
    down.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="the user's own message in T3 Code, in place of --by, --at and the words",
    )
    down.add_argument(
        "--from",
        dest="recorder",
        metavar="THREAD",
        help="the thread running this: a word recorded by a project's home is not posted to it",
    )
    down.add_argument("words", nargs="*", help="the user's words, with --by and --at")


VERBS = (
    verbs.Verb(
        "word",
        "the user's word to a project's home, or to every home",
        _down,
        _word,
        abbrev=False,
    ),
)


def _deliver(half: Half) -> None:
    """`deliver` as a step: a `words.json` that does not parse is a gate, and the pass goes on."""
    try:
        deliver(half.run, half.client)
    except Unparsable:
        half.run.gate(half.run.project.name, "words.json does not parse", str(path(half.run.state)))


def scratch(
    config: Config, client: Client | None, now: datetime, say: Callable[[str], None]
) -> None:
    """The whole pass of each scratch home, a chore of the pass: its words that wait go to its
    thread. A scratch home is no project of the pass (`jbus.load`), so it is no step of one.
    One whose `words.json` does not parse is said, and is no gate: a scratch home has no
    webhook to ask it on."""
    for one in config.scratch:
        run = Pass(config, one.addressee(), now, say)
        try:
            deliver(run, client)
        except Unparsable as error:
            say(f"wait {one.name}: {error}")


STEPS = (verbs.Step("before-watch", 10, "word.deliver", _deliver),)
CHORES = (verbs.Chore(20, "the scratch homes", scratch),)
