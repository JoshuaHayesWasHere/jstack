"""The user's word, carried down to a home: one record that `jbus word` writes and jbus sends.

A word is an approval or an instruction that answers no open question. The user says it
wherever they are, and a home records it with `jbus word --message`, which reads the user's own
message from T3 Code. A word is an act (`jbus.acts`): one line of the project's `acts.jsonl`
whose verb is `word`, kept once, with:

- `id`: the first 12 characters of a hash of the project, the words, the user and the time, and
  of `ref` when there is one, and of the scope for `--scope`. So the same word for the same
  project is the same act however often the command runs.
- the subject: the scope of the home the word is for, or empty for the root home (`owner`).
- the evidence: the user's words, when they said them, and the message (`t3-message`, checked)
  or the view (`view`) they were said in.
- the line: `kept`, or why jbus posts the word to nobody (`skipped`). A word said in, or
  recorded by, the home that the word is for is done at once, and nobody tells the home what it
  recorded itself.

What became of a word is no act, since it changes: `word-sends.json` in the state directory
maps each word's id to the home's thread that received it and when (`thread`, `sent_at`), or to
why it has not gone yet (`waits`). `Word` is the read model of the two (`load`).

The file of words jbus kept before words were acts is not read: a word it kept and never sent is
said again with `jbus word --message`.

A word goes to one home of the project, the one that owns its subject (`owner`): the home whose
directory or brief the page it was given on (`--page`) is of, else the home of the briefs, requests
and rows its words name by slug, when they are all one home's, else the home it was said in (the
thread of `--message`) or recorded by (`--from`), else the root home. So a word about a scoped
home's work reaches that home alone, a scoped home's own word that names no other home's work stays
in that scope, and two homes never act on one word. A home that records a word about another home's
work with `--from` forwards it to the home that owns it.

`--scope <scope>`, given again for each scope or once as `--scope every`, carries one word to the
scoped homes it names in place of `owner`'s one home: the root home runs it for the user's word to
those homes, and writes no words of its own into them. It takes only `--message`, so the words are
checked as the user's own. It keeps one record for each scope, whose id hashes the scope too, and
none for a scope that already holds the same word, by any path: the command says `held` for it.
Each new one goes to its scope's thread at once, as a word of its own.

A word goes once, as one queued message to the thread in that home's `home-id`. jbus reads that file
when it sends the word, not when it keeps it (`jbriefs.home.thread_of`). The command sends the word
at once, except to the home that recorded it. For a word said in that home's own thread (`--message`
whose thread is the home's) or recorded by it (`--from <thread id>`), `keep` records the word as
sent, with `skipped` saying why. With `--all`, `keep` does so only for the copy of the project whose
home recorded the word. A home that handed off and has no `home-id` has no thread to send to, so a
word for that home waits for the next home like any other word. A word that could not go waits,
and each pass tries it again (`deliver`). A home with no `home-id`, or one that handed off, gets
the word on the first pass after the next home starts and writes its own id into `home-id`. The
retry key is `word|<project>|<id>|<thread>`, and jbus writes `sent_at` only after T3 Code accepted
the message.

No part of a word is an event. A word is in no outbox, so no wake carries it, and whoever ran the
command hears nothing back. The log still has a line
for the word (`wake.Box.record`), which `jbus events` prints. The line holds the words, `by`, `at`,
and `to`, which is the thread that received the word, or nothing while the word waits or when jbus
posted it to nobody. A word that T3 Code refuses gets such a line too, and waits like any other.

The command holds no lock of the pass, so a pass and the command can both hold the same unsent word.
For that reason, under `word-sends.lock`, jbus rereads `word-sends.json`, writes what became of
the word into it, and never changes a word that has `sent_at` again (`_change`).

A `word-sends.json` that does not parse, or that holds something other than a map of records, is
`Unparsable`. jbus does not write over such a file, and a pass reports it in a gate and goes on.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import jsettings
from jbriefs.home import home_of, scopes, thread_of
from jbus import Config, Project, Refused, acts, locked, outbox, party, queue, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.t3 import heard as heard_in

if TYPE_CHECKING:
    from jbus.cli import Half

LOCK = "word-sends.lock"
NAME = "word-sends.json"
KIND = "word"
KEPT = "kept"
MESSAGE = (
    "jbus: this is {by}'s own word, said {at} and carried to this home by jbus. Take it as "
    "said by {by} in this thread. It answers no open question, and nothing is sent back "
    "for it. It is word {id}: a row it approves is approved with --word {id}.\n\n{words}"
)
NO_HOME = "its home has no home-id, so it goes on the pass after that home's next start"
NO_T3 = "jbus is not signed in to T3 Code"
NO_ANSWER = "T3 Code gave no answer"
REFUSED = "T3 Code refused it"
CAPPED = "its home's thread is capped, so it goes on the first pass after the reset"
SAID_IN_HOME = "it was said in this project's own home thread {thread}"
BY_HOME = "it was recorded by this project's home thread {thread}"
THREAD = re.compile(r"mcp:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
EVERY = "every"
SLUG = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*(?:-[a-z0-9]+(?:\.[a-z0-9]+)*)+")


class Unparsable(Refused):
    """`word-sends.json` is not what this module writes, so jbus does not write over it."""


@dataclass(frozen=True)
class Word:
    """A word as its act and `word-sends.json` have it. `by` is the party that kept it, as
    `<kind>/<route>`: the words are the user's own."""

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
    home: str = ""


def path(state: Path) -> Path:
    return state / NAME


def _sends(state: Path) -> dict[str, dict[str, str]]:
    """What became of each word, by its id. `_sends` takes no lock and writes nothing."""
    file = path(state)
    if not file.exists():
        return {}
    try:
        found = json.loads(file.read_text())
    except (OSError, ValueError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error
    if not isinstance(found, dict) or not all(isinstance(one, dict) for one in found.values()):
        raise Unparsable(f"refused: {file} is not a map of words, and nothing writes it")
    return found


def load(state: Path) -> list[Word]:
    """Return every word of the project, oldest first: each word act, with what became of it.
    `load` takes no lock and writes nothing."""
    sends = _sends(state)
    try:
        kept = acts.read(state)
    except (OSError, ValueError) as error:
        raise Unparsable(f"refused: {acts.path(state)} does not parse") from error
    words: list[Word] = []
    for one in kept:
        if one["action"]["verb"] != KIND or one["id"] in {each.id for each in words}:
            continue
        said, who, line = one["evidence"], one["party"], one["line"]
        made = Word(
            id=one["id"],
            words=said["words"],
            by=f"{who['kind']}/{who['route']}",
            at=said["said_at"],
            kept_at=one["at"],
            ref=said["ref"],
            said_in=said["said_in"],
            checked=said["checked"],
            skipped="" if line == KEPT else line,
            home=one["action"]["subject"],
        )
        sent = sends.get(made.id, {})
        words.append(
            replace(
                made,
                thread=str(sent.get("thread", "")),
                sent_at=str(sent.get("sent_at", "")),
                waits=str(sent.get("waits", "")),
            )
        )
    return words


def _whose(home: Path, brief: Path) -> str:
    found = home_of(home, brief.read_text(errors="replace"))
    return "" if found == home else found.name


def _named(home: Path, name: str) -> str | None:
    """The scope of the home whose brief or request has the slug `name`, empty for the root home,
    or None when no brief or request has it. A slug that no brief or request has yet is a scope's
    when every brief and request that starts with its prefix, the slug up to its first dash, is
    that scope's: a new `fl-` slug where every `fl-` brief is the flow home's."""
    for kind in ("tasks", "scouts"):
        brief = home / kind / f"{name}.md"
        if brief.is_file():
            return _whose(home, brief)
    prefix = name.split("-")[0] + "-"
    found = {
        _whose(home, brief)
        for kind in ("tasks", "scouts")
        for brief in (home / kind).glob(f"{prefix}*.md")
        if brief.is_file()
    }
    return found.pop() if len(found) == 1 and "" not in found else None


def _decided(home: Path, words: str, page: str) -> str | None:
    """The scope that a page or the words' slugs give a word (`owner`), or None when neither
    decides."""
    if page:
        where = Path(page).resolve()
        if where.is_relative_to(home.resolve()):
            parts = where.relative_to(home.resolve()).parts
            if parts[:1] and parts[0] in {scope.name for scope, _, _ in scopes(home)}:
                return parts[0]
            for part in parts[1:]:
                found = _named(home, Path(part).name.removesuffix(".html"))
                if found is not None:
                    return found
    named = {_named(home, slug) for slug in SLUG.findall(words)} - {None}
    if len(named) == 1:
        return named.pop() or ""
    return "" if named else None


def owner(home: Path, words: str, page: str = "", *threads: str) -> str:
    """The scope of the home that owns a word's subject, or an empty string for the root home.

    A page under a scope's directory is that scope's, and a page named for a brief or a request,
    as `reports/<slug>/` or `reports/<slug>.html`, is the home's of that brief or request. A page
    decides over the words. Without one, the briefs, requests and rows that the words name by slug
    decide when they are all one home's (`_named`), and a word that names the work of two homes is
    the root home's. A word that names none is the home's whose thread is the first of `threads`
    that is a home's thread: the thread it was said in, then the one that recorded it. So a scoped
    home's own word stays in that scope. With no such thread, it is the root home's."""
    decided = _decided(home, words, page)
    if decided is not None:
        return decided
    homes = {thread_of(home): "", **{thread_of(scope): scope.name for scope, _, _ in scopes(home)}}
    homes.pop("", None)
    return next((homes[one] for one in threads if one in homes), "")


def _homes_dir(run: Pass, one: Word) -> Path:
    return run.home / one.home if one.home else run.home


def _write(state: Path, sends: dict[str, dict[str, str]]) -> None:
    write_json(path(state), sends, mode=0o600)


def said(words: str) -> str:
    """Return the words as jbus keeps them, on one line, and refuse none."""
    words = " ".join(words.split())
    if not words:
        raise Refused("refused: a word has the user's words")
    return words


def keep(
    run: Pass,
    who: party.Party,
    heard: party.Evidence,
    recorder: str = "",
    page: str = "",
    scope: str | None = None,
) -> Word:
    """Keep a word for the project as an act of `who`, and return its record: the one there was,
    or a new one.

    `heard` is the user's words, read by jbus from a T3 Code message (`ref` is then the message's
    `<thread id>/<message id>`) or given in the view. `recorder` is the thread that ran
    `jbus word`, for `--from`, and `page` the page it was given on, for `--page`. A new word is for
    the home that `owner` names. When it was said in that home's thread, or recorded by that
    thread, `keep` records the word as sent to that thread and posts it to nobody (`skipped`).

    With `scope`, the word is for that scoped home and no other, and its id hashes the scope too.
    A home that already holds the same word, kept by any path, gets no second act: `keep`
    returns the one it holds.

    The act is logged under `acts.lock` with `acts.logged`, not through `acts.act`, since a word
    has no door and `keep` must find a word that is kept already and log a new one at once.
    """
    words, at, ref = said(heard.words), heard.said_at, heard.ref
    extra = [*([ref] if ref else []), *([f"scope:{scope}"] if scope is not None else [])]
    named = json.dumps([run.project.name, words, run.user.user, at, *extra])
    name = hashlib.sha256(named.encode()).hexdigest()[:12]
    heard = replace(heard, words=words)
    with locked(run.state, acts.LOCK):
        whose = scope
        if whose is None:
            whose = owner(run.home, words, page, ref.partition("/")[0], recorder)
        for one in load(run.state):
            if one.id == name or (one.words, one.at, one.ref, one.home) == (words, at, ref, whose):
                return one
        mine = thread_of(run.home / whose if whose else run.home)
        skipped = ""
        if mine and mine == ref.partition("/")[0]:
            skipped = SAID_IN_HOME.format(thread=mine)
        elif mine and mine == recorder:
            skipped = BY_HOME.format(thread=mine)
        made = acts.logged(
            run, who, party.Action(KIND, whose), heard, "done", skipped or KEPT, id=name
        )
    if skipped:
        with locked(run.state, LOCK):
            sends = _sends(run.state)
            sends[name] = {"thread": mine, "sent_at": made.at, "waits": ""}
            _write(run.state, sends)
        about = {"words": words, "by": run.user.user, "at": at, "to": ""}
        run.box.record(KIND, f"{KIND} {run.project.name}: kept, {skipped}", words, word=about)
    (kept,) = [one for one in load(run.state) if one.id == name]
    return kept


def basis(state: Path, name: str) -> queue.Said:
    """Return the word with that id, as the basis of an approval. Refuse an id the file does
    not have."""
    for one in load(state):
        if one.id == name:
            return queue.Said(one.words, one.at, one.said_in, one.checked, one.ref)
    raise Refused(f"refused: {acts.path(state)} has no word {name}")


def _change(run: Pass, one: Word, **changed: str) -> bool:
    """Write what became of a word, add its line to the log, and return whether it wrote
    anything. When jbus sent the word after the caller read `one`, `_change` leaves the word
    as it is."""
    with locked(run.state, LOCK):
        sends = _sends(run.state)
        if sends.get(one.id, {}).get("sent_at"):
            return False
        now = replace(one, **changed)
        sends[one.id] = {"thread": now.thread, "sent_at": now.sent_at, "waits": now.waits}
        _write(run.state, sends)
    how = f"sent to {now.thread}" if now.sent_at else f"waits, {now.waits}"
    about = {"words": now.words, "by": run.user.user, "at": now.at, "to": now.thread}
    run.box.record(KIND, f"{KIND} {run.project.name}: {how}", now.words, word=about)
    return True


def post(
    run: Pass,
    client: Client | None,
    thread: str,
    message: str,
    key: str,
    *,
    row: str,
    template: str,
) -> str:
    """Send one queued message to a home's thread, under the retry key `key`, so T3 Code takes
    a second send with the same key as a repeat of the first. Return why it did not go, or nothing
    when T3 Code took it."""
    if not thread or client is None:
        return NO_T3 if thread else NO_HOME
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=row,
            key=key,
            text=message,
            template=template,
            needs="act",
        )
    except T3Refused:
        return REFUSED
    except T3Error:
        return NO_ANSWER
    return "" if went else CAPPED


def deliver(run: Pass, client: Client | None) -> None:
    """Send each word that waits to the thread of the home it is for, once. A word that cannot go
    keeps waiting.

    `deliver` writes why a word waits once, and again when the reason changes.
    """
    for one in load(run.state):
        if one.sent_at:
            continue
        thread, name = thread_of(_homes_dir(run, one)), run.project.name
        key = f"{KIND}|{name}|{one.id}|{thread}"
        text = MESSAGE.format(**(asdict(one) | {"by": run.user.user}))
        waits = post(run, client, thread, text, key, row=name, template=KIND)
        if not waits:
            at = jsettings.stamp(run.now)
            if _change(run, one, thread=thread, sent_at=at, waits=""):
                run.say(f"{KIND} {name}: sent to {thread}")
            continue
        if waits != one.waits and _change(run, one, waits=waits):
            run.say(f"wait {name}: a word of {one.at} {waits}")


def line(run: Pass, was: Word) -> str:
    """Return what `jbus word` prints for one project: the current state of the word that it
    kept as `was`."""
    (one,) = [one for one in load(run.state) if one.id == was.id]
    name = run.project.name
    if one.skipped:
        return f"kept: {name}, not posted, {one.skipped}, word {one.id}"
    if one.sent_at:
        how = "already sent" if was.sent_at else "sent"
        to = f"the {one.home} home at {one.thread}" if one.home else one.thread
        return f"{how}: {name}, to {to}, word {one.id}"
    whose = f"for the {one.home} home, " if one.home else ""
    return f"waits: {name}, {whose}{one.waits}, word {one.id}"


def recorded_by(recorder: str, homes: list[str], client: Client | None) -> str:
    """Check `--from` before anything is kept. Refuse a value that is not shaped like a T3 Code
    thread id, `mcp:<uuid>` as a home's `home-id` holds it, and one that is neither a home's thread
    nor a thread T3 Code has. Return a line to print when T3 Code gave no answer, so that the shape
    alone decided, or nothing."""
    if not THREAD.fullmatch(recorder):
        raise Refused(f'refused: --from is a T3 Code thread id, mcp:<uuid>, not "{recorder}"')
    if recorder in homes:
        return ""
    try:
        if client is None:
            raise T3Error(NO_T3)
        client.call("t3_thread_read", {"threadId": recorder, "limit": 1})
    except T3Refused as error:
        if GONE.search(str(error)):
            raise Refused(
                f"refused: --from {recorder} is no thread of T3 Code, and not this home's"
            ) from error
    except T3Error:
        pass
    else:
        return ""
    return (
        f"unchecked: --from {recorder} has the shape of a thread id, and T3 Code gave no answer "
        "on whether it has that thread"
    )


TYPED = (
    "refused: a word is the user's own message, --message <thread id>/<message id>, which jbus "
    "reads from T3 Code: a word typed with --by and --at is not taken"
)


def _evidence(heard: queue.Said) -> party.Evidence:
    """The user's message that jbus read, as the evidence of the word's act."""
    return party.Evidence(
        "t3-message", heard.ref, heard.words, heard.said_at, heard.said_in, heard.checked
    )


def _word(args: argparse.Namespace, config: Config) -> int:
    """`jbus word`: keep the user's word for one project's home, or for every home, from any
    checkout.

    The command keeps the word and sends it at once to the thread in the home's `home-id`.
    The same message for the same project is the same word, so a second run sends nothing
    again. The word is a message named with `--message`, and jbus reads that message's words
    and time from T3 Code: a word typed with `--by` and `--at` is no longer taken. For a word
    said in a project's home thread, or recorded by it (`--from`), `keep` records the word
    as sent and posts it to nobody. Before it keeps anything, the command refuses a `--from`
    that names no thread (`recorded_by`), since a mistyped id would post the word back to the
    home that recorded it.

    The word goes to the home of the project that owns its subject (`owner`), so a home that
    records a word about another home's work forwards it there, and a word that names no home's
    work stays with the home it was said in or recorded by.

    `--to` names a project or a scratch home (`jbus.Scratch`). `--all` means every project
    and no scratch home, since a scratch home takes no word about the repos. When a project
    refuses the word, for example because its `word-sends.json` does not parse, the command says
    so and skips that project. The other projects still get the word, and the command then
    exits 1.
    """
    projects = config.projects if args.all else (config.addressee(args.to),)
    if args.message is None:
        raise Refused(TYPED)
    heard = _evidence(heard_in(config, args.message))
    who = acts.cli_party(args, heard)
    try:
        client = Client(config.server, config.token_path)
    except Refused:
        client = None
    now = datetime.now(UTC)
    if args.recorder is not None:
        homes = [
            thread_of(where)
            for project in projects
            for home in [Pass(config, project, now, lambda _: None).home]
            for where in (home, *(scope for scope, _, _ in scopes(home)))
        ]
        unchecked = recorded_by(args.recorder, homes, client)
        if unchecked:
            print(unchecked)
    if args.scopes:
        return _scoped(args, config, projects, who, heard, client, now)
    code = 0
    for project in projects:
        run = Pass(config, project, now, lambda _: None)
        try:
            was = keep(run, who, heard, args.recorder or "", args.page or "")
            deliver(run, client)
            print(line(run, was))
        except Refused as error:
            print(error)
            code = 1
    return code


def _scoped(
    args: argparse.Namespace,
    config: Config,
    projects: tuple[Project, ...],
    who: party.Party,
    heard: party.Evidence,
    client: Client | None,
    now: datetime,
) -> int:
    """`jbus word --scope`: keep the user's message as one word for each scoped home named, send
    each new one to its home's thread, and say for each whether it went, waits, or is held there
    already."""
    if args.all:
        raise Refused("refused: --scope names the scoped homes of the project --to names")
    (project,) = projects
    run = Pass(config, project, now, lambda _: None)
    known = [scope.name for scope, _, _ in scopes(run.home)]
    named = known if EVERY in args.scopes else list(dict.fromkeys(args.scopes))
    if not named:
        raise Refused(f"refused: {project.name} has no scoped home for --scope {EVERY}")
    unknown = [one for one in named if one not in known]
    if unknown:
        raise Refused(f"refused: --scope {unknown[0]} is no scoped home of {project.name}")
    before = {one.id for one in load(run.state)}
    kept: list[tuple[str, Word]] = []
    for scope in named:
        was = keep(run, who, heard, args.recorder or "", scope=scope)
        kept.append((scope, was) if was.id in before else ("", was))
        before.add(was.id)
    deliver(run, client)
    for held, was in kept:
        if held:
            print(
                f"held: {project.name}, the {held} home holds word {was.id}, so it is not sent "
                "again"
            )
        else:
            print(line(run, was))
    return 0


def _down(down: argparse.ArgumentParser) -> None:
    homes = down.add_mutually_exclusive_group(required=True)
    homes.add_argument(
        "--to", metavar="PROJECT", help="the project or the scratch home whose home it is for"
    )
    homes.add_argument("--all", action="store_true", help="the home of every project")
    down.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="the user's own message in T3 Code, which jbus reads for the words and the time",
    )
    down.add_argument(
        "--from",
        dest="recorder",
        metavar="THREAD",
        help="the thread running this: a word recorded by a project's home is not posted to it",
    )
    down.add_argument(
        "--page",
        metavar="FILE",
        help="the page the word was given on: the word goes to the home whose page it is",
    )
    down.add_argument(
        "--scope",
        dest="scopes",
        action="append",
        default=[],
        metavar="SCOPE",
        help=f"a scoped home the user's message goes to, given again for each, or {EVERY}",
    )


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
    """Run `deliver` as a step. A `word-sends.json` that does not parse raises a gate, and the pass
    goes on."""
    try:
        deliver(half.run, half.client)
    except Unparsable:
        half.run.gate(half.run.project.name, f"{NAME} does not parse", str(path(half.run.state)))


def scratch(
    config: Config, client: Client | None, now: datetime, say: Callable[[str], None]
) -> None:
    """For each scratch home, send the home's waiting words to the home's thread. That is all
    the work a scratch home gets from jbus, and `jbus.cli.poll` runs `scratch` once a pass as
    a chore. A scratch home is not one of the projects that a pass works through
    (`jbus.load`), so `scratch` cannot be one of a project's steps. When a scratch home's
    `word-sends.json` does not parse, `scratch` says so and raises no gate, since a scratch home
    has no outbox that could take a gate."""
    for one in config.scratch:
        run = Pass(config, one.addressee(), now, say)
        try:
            deliver(run, client)
        except Unparsable as error:
            say(f"wait {one.name}: {error}")


STEPS = (verbs.Step("before-watch", 10, "word.deliver", _deliver),)
CHORES = (verbs.Chore(20, "the scratch homes", scratch),)
