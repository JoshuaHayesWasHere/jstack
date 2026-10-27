"""`jbus noticed`: keep each `Noticed` line of the briefs and the scout requests as one
record, which a home marks taken or dropped.

A crewmate's Result and a scout's Report end with a `Noticed:` line, and a Review has a
`Noticed, from the review:` line. On that line a thread writes down what is wrong outside its task.
Each pass reads them all, in `tasks/*.md` and `scouts/*.md` of the home's state directory: every
`## Result` (a follow-up included), `## Review` and `## Report` section. The line starts with
`Noticed`, and a colon ends its label. A few words may come between the two, after a comma or in
parentheses. The text after the colon is one record, and each item of the list under the line is one
more (`lines`). So a line added to the list later is one new record. jbus makes no record of a text
that is empty or says `none`.

`noticed.json` in the project's state directory is `{"records"}`, each a `Record`:

- `key`: `<slug>:<the first 12 of the sha256 of its text>`. A pass that finds the same text
  of the same slug again adds nothing, so two passes add no more than one pass does;
- `slug`, `kind` (`tasks` or `scouts`), `section` (its heading, with no `## `) and `label`
  (the words before the colon): where a pass first found it;
- `text`: the whole text;
- `seen_at`: when a pass first found it, in UTC;
- `mark`: `new`, `taken` or `dropped`. Only `take` or `drop` changes a record's mark, and only once,
  from `new`. `row` is the queue row or plan entry that took it up, and `why` says why the marker
  dropped it. `by` and `at` say who marked it and when, copied from `--by` and `--at`.

A home also keeps a record for another home of the project with `jbus noticed add --for <scope or
root> --from <its own thread> "<text>"`: what it found that is that home's to act on. That record
has `for`, the home it is for, `from`, the home that kept it, `kind` `homes`, the slug `home` for
the root or `home-<scope>` for a scope, as the home skill names a home, and the section `from
<that home>`. So the same text for the same home twice is one record, as a brief's line is. No home
sends another a message for it: a pass wakes the home it is for once, with every new record for
that home and every word the root carried to it by `jbus word --scope` (`wake`), and `told` is when
that wake went. `jbus noticed --for <home>` lists that home's new ones, and `jbus noticed` with no
`--for` lists only the briefs' and requests' lines, as before. A record keeps `for`, `from` and
`told` in `noticed.json` only when they are set, so a record from before stays as it was.

A project's first pass finds no file. It marks every line that exists then as `dropped`, with the
why `FROM_BEFORE` and with `by` set to jbus. jbus does not count a line as new when the threads
wrote it before jbus kept the list. jbus writes nothing into a brief, asks nobody about a line and
makes no queue row for one. When the file does not parse, every verb that would write it refuses
(`Unparsable`), and a pass says so and leaves the file as it is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import jbus
import jsettings
from jbriefs.home import scopes, thread_of
from jbus import locked, mirror, outbox, plan, queue, verbs, word, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error

if TYPE_CHECKING:
    from jbus.cli import Half

LOCK = "noticed.lock"
NAME = "noticed.json"
NEW, TAKEN, DROPPED = "new", "taken", "dropped"
MARKS = (NEW, TAKEN, DROPPED)
FROM_BEFORE = "from before the list"
JBUS = "jbus"
SECTIONS = ("## Result", "## Review", "## Report")
_LABEL = re.compile(r"(Noticed(?:,[^:\n]*| \([^)\n]*\))?):(.*)")
_ITEM = re.compile(r"[-*] ")
_NONE = re.compile(r"none\.?", re.I)
_NAME = re.compile(r"[^\s,]+")
HOMES = "homes"
ROOT = "root"
WAKE = "records"
SHOWN = 600
"""How many characters of a word the wake carries: the rest is in `words.json`, by its id."""
_JSON = {"for_": "for", "from_": "from"}
_FIELDS = {value: name for name, value in _JSON.items()}


class Unparsable(jbus.Refused):
    """`noticed.json` is not in the form this module writes, so this module writes nothing
    over it."""


@dataclass(frozen=True)
class Record:
    key: str
    slug: str
    kind: str
    section: str
    label: str
    text: str
    seen_at: str
    mark: str = NEW
    row: str = ""
    why: str = ""
    by: str = ""
    at: str = ""
    for_: str = ""
    from_: str = ""
    told: str = ""

    def line(self) -> str:
        """Return the record as one line: its key, where it is from, its mark, and its text."""
        said = {TAKEN: f" by {self.row}", DROPPED: f": {self.why}"}.get(self.mark, "")
        text = " ".join(self.text.split())
        return f"{self.key} {self.slug}, {self.section}, {self.mark}{said}: {text}"


def kept(one: Record) -> dict[str, str]:
    """Return the record as `noticed.json` keeps it: `for` and `from` by those names, and the
    three fields of a record for a home only when they are set."""
    made = {_JSON.get(name, name): value for name, value in asdict(one).items()}
    return {
        name: value for name, value in made.items() if value or name not in ("for", "from", "told")
    }


def key(slug: str, text: str) -> str:
    return f"{slug}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def lines(body: str) -> Iterator[tuple[str, str]]:
    """Return each item of each `Noticed` line of a section: its label and its text.

    The text after the colon is one item. Under it, each line that starts with `- `, `* ` or a
    lowercase letter is one more item, such as a `follow-up: <finding>` line. An indented
    line belongs to the item above it. The list ends at a blank line, a heading, or a line
    that starts with a capital, such as `Left:`. So a line added under the list later is one
    more item and leaves the others as they were.
    """
    rows = body.splitlines()
    for at, row in enumerate(rows):
        found = _LABEL.fullmatch(row.rstrip())
        if not found:
            continue
        items = [[found[2].strip()]]
        for under in rows[at + 1 :]:
            if _ITEM.match(under):
                items.append([_ITEM.sub("", under, count=1).strip()])
            elif under[:1] in (" ", "\t") and under.strip():
                items[-1].append(under.strip())
            elif under[:1].islower():
                items.append([under.strip()])
            else:
                break
        for item in items:
            text = "\n".join(item).strip()
            if text and not _NONE.fullmatch(text):
                yield found[1], text


def found(home: Path, now: datetime) -> list[Record]:
    """Return every record the briefs and requests have now, each once, as a new record seen
    at `now`."""
    made: dict[str, Record] = {}
    seen = jsettings.stamp(now)
    for kind in ("tasks", "scouts"):
        for path in sorted((home / kind).glob("*.md")):
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for heading, body in mirror.sections(text):
                if not heading.startswith(SECTIONS):
                    continue
                for label, said in lines(body):
                    one = key(path.stem, said)
                    made.setdefault(
                        one, Record(one, path.stem, kind, heading[3:], label, said, seen)
                    )
    return list(made.values())


def path(state: Path) -> Path:
    return state / NAME


def read(state: Path) -> list[Record] | None:
    """Return every record as the file keeps it, or None where there is no file yet. Raise
    `Unparsable` when the file is not in the form this module writes."""
    file = path(state)
    if not file.exists():
        return None
    try:
        records = [
            Record(**{_FIELDS.get(name, name): value for name, value in one.items()})
            for one in json.loads(file.read_text())["records"]
        ]
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error
    if any(one.mark not in MARKS for one in records):
        raise Unparsable(f"refused: {file} has a mark that is not one of {', '.join(MARKS)}")
    return records


def _write(state: Path, records: list[Record]) -> None:
    write_json(path(state), {"records": [kept(one) for one in records]})


def keep(state: Path, home: Path, now: datetime, *, before: frozenset[str] = frozenset()) -> int:
    """Add what is new, and return how many records this function added. On the first pass it adds
    every line that exists, marked dropped with the why `FROM_BEFORE`. It does the same for every
    line of the files `before` names, which look like `tasks/<slug>.md` or `scouts/<slug>.md`: the
    ones `mirror.scan` found restored."""
    with locked(state, LOCK):
        records = read(state)
        first = records is None
        records = records or []
        known = {one.key for one in records}
        stamp = jsettings.stamp(now)
        added = [
            replace(one, mark=DROPPED, why=FROM_BEFORE, by=JBUS, at=stamp)
            if first or f"{one.kind}/{one.slug}.md" in before
            else one
            for one in found(home, now)
            if one.key not in known
        ]
        if added or first:
            _write(state, records + added)
        return len(added)


def scan(run: Pass) -> None:
    try:
        keep(run.state, run.home, run.now)
    except Unparsable as error:
        run.condition("noticed", str(error), key=f"noticed unparsable {run.day}")


def _named(state: Path, home: Path, slug: str) -> bool:
    """Return whether any home has a queue row or a plan entry with the slug, open or
    done."""
    try:
        rows = queue.load(state)
    except queue.Unparsable as error:
        raise jbus.Refused(f"refused: {error}, so no row can be named") from error
    if any(row.get("slug") == slug for row in rows):
        return True
    folders = sorted(one for one in home.glob("*") if one.is_dir())
    for folder in (home, *folders):
        for name in ("plan.md", "plan-done.md"):
            try:
                text = (folder / name).read_text(errors="replace")
            except OSError:
                continue
            if any(entry.slug == slug for entry in plan.entries(text)):
                return True
    return False


def mark(
    state: Path,
    home: Path,
    given: str,
    by: str,
    at: str,
    user: jsettings.Settings,
    *,
    row: str = "",
    why: str = "",
) -> str:
    """Mark one new record taken by `row`, or dropped for `why`. Refuse anything else."""
    if not _NAME.fullmatch(by):
        raise jbus.Refused(f"refused: --by is one name with no comma, not {by!r}")
    if not user.takes(at):
        raise jbus.Refused(f'refused: --at is "{user.form(at)}"')
    if not row and not why.strip():
        raise jbus.Refused("refused: --why says why it is dropped, in words")
    if row and not _named(state, home, row):
        raise jbus.Refused(f"refused: {row} is no queue row and no plan entry")
    with locked(state, LOCK):
        records = read(state) or []
        at_key = [n for n, one in enumerate(records) if one.key == given]
        if not at_key:
            raise jbus.Refused(f"refused: no noticed line has the key {given}")
        one = records[at_key[0]]
        if one.mark != NEW:
            raise jbus.Refused(f"refused: {one.line()}, and a line is marked once")
        if row:
            records[at_key[0]] = replace(one, mark=TAKEN, row=row, by=by, at=at)
        else:
            records[at_key[0]] = replace(one, mark=DROPPED, why=" ".join(why.split()), by=by, at=at)
        _write(state, records)
        return records[at_key[0]].line()


def homes(home: Path) -> dict[str, Path]:
    """Return each home of the project by the name `--for` takes, `root` or a scope's, with its
    directory."""
    return {ROOT: home, **{scope.name: scope for scope, _, _ in scopes(home)}}


def add(state: Path, home: Path, now: datetime, to: str, sender: str, text: str) -> tuple[str, str]:
    """Keep one record for the home `to` from the home whose thread is `sender`. Return `kept` or
    `already kept`, and the record's line. Refuse a home the project does not have, a thread that
    is no home's, and a home that keeps a record for itself."""
    named = homes(home)
    if to not in named:
        raise jbus.Refused(f"refused: --for {to} is no home of this project: {', '.join(named)}")
    thread = jsettings.thread_id(sender)
    froms = [
        name for name, where in named.items() if jsettings.thread_id(thread_of(where)) == thread
    ]
    if not thread or not froms:
        raise jbus.Refused(f"refused: --from {sender} is the thread of no home of this project")
    if to in froms:
        raise jbus.Refused(f"refused: --from {sender} is the {to} home's own thread")
    text = text.strip()
    if not text or _NONE.fullmatch(text):
        raise jbus.Refused("refused: a record has a text, and not none")
    if read(state) is None:
        keep(state, home, now)
    slug = "home" if to == ROOT else f"home-{to}"
    made = Record(
        key(slug, text),
        slug,
        HOMES,
        f"from {froms[0]}",
        "Noticed",
        text,
        jsettings.stamp(now),
        for_=to,
        from_=froms[0],
    )
    with locked(state, LOCK):
        records = read(state) or []
        found = [one for one in records if one.key == made.key]
        if found:
            return "already kept", found[0].line()
        _write(state, [*records, made])
    return "kept", made.line()


def _told(state: Path, keys: set[str], at: str) -> None:
    with locked(state, LOCK):
        records = read(state) or []
        _write(
            state,
            [replace(one, told=at) if one.key in keys and not one.told else one for one in records],
        )


def _shown(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SHOWN else f"{text[:SHOWN]}... (the rest is in words.json)"


def message(project: str, to: str, mine: list[Record], theirs: list[word.Word]) -> str:
    """Return the one wake a home gets for its new records: how many of each, the command that
    lists the noticed ones, and each word in full, as `word.MESSAGE` frames a word."""
    said = [
        f"jbus: {len(mine)} noticed and {len(theirs)} words are new for this home. No home "
        "sent you a message for them."
    ]
    if mine:
        said.append(
            f"- {len(mine)} noticed, kept for this home by another home: list them with "
            f"`jbus --project {project} noticed --for {to}`, and mark each once with take or drop."
        )
    for one in theirs:
        said.append(
            f"- word {one.id}: {one.by}'s own word, said {one.at} and carried to this home by "
            f"jbus. Take it as said by {one.by} in this thread. It answers no open question, "
            "and nothing is sent back for it. A row it approves is approved with "
            f"--word {one.id}.\n\n"
            f"{_shown(one.words)}"
        )
    return "\n\n".join(said)


def wake(run: Pass, client: Client) -> None:
    """Wake each home that has new records once: the noticed ones for it that no wake has told,
    and the words `jbus word --scope` kept for it that no wake has carried. The one message goes
    through the outbox, which holds it while the home has a turn running or was told this pass, and
    its key is the records it names, so a pass that sends it again sends nothing new. A home with
    no thread in its `home-id` is woken on the first pass after its start."""
    try:
        records = read(run.state) or []
    except Unparsable:
        return
    try:
        words = word.load(run.state)
    except word.Unparsable:
        words = []
    for name, where in homes(run.home).items():
        mine = [one for one in records if one.for_ == name and one.mark == NEW and not one.told]
        theirs = [
            one
            for one in words
            if one.via == word.RECORDS and (one.home or ROOT) == name and not one.sent_at
        ]
        thread = thread_of(where)
        if not (mine or theirs) or not thread:
            continue
        named = sorted([one.key for one in mine] + [one.id for one in theirs])
        tag = hashlib.sha256("\n".join(named).encode()).hexdigest()[:12]
        text = message(run.project.name, name, mine, theirs)
        slug = "home" if name == ROOT else f"home-{name}"
        try:
            went = outbox.send(
                run,
                client,
                thread=thread,
                row=slug,
                key=f"{WAKE}|{name}|{tag}",
                text=text,
                template=WAKE,
                needs="act",
            )
        except T3Error:
            continue
        if not went:
            continue
        at = jsettings.stamp(run.now)
        _told(run.state, {one.key for one in mine}, at)
        for one in theirs:
            word.carried(run, one, thread, at)
        run.say(
            f"{WAKE} {run.project.name}: woke the {name} home for {len(mine)} noticed and "
            f"{len(theirs)} words"
        )


def _noticed(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state, home = config.state(project), config.home(project)
    if args.verb == "take":
        print(mark(state, home, args.key, args.by, args.at, config.user, row=args.row))
        return 0
    if args.verb == "drop":
        print(mark(state, home, args.key, args.by, args.at, config.user, why=args.why))
        return 0
    if args.verb == "add":
        how, line = add(state, home, datetime.now(UTC), args.home, args.sender, " ".join(args.text))
        print(f"{how}: {line}")
        return 0
    records = read(state)
    if records is None:
        print("none: no pass has read the Noticed lines yet")
        return 0
    shown = [one for one in records if one.for_ == args.listed and (args.all or one.mark == NEW)]
    shown.sort(key=lambda one: (one.seen_at, one.key), reverse=True)
    if args.json:
        print(json.dumps([kept(one) for one in shown], indent=2))
    elif not shown:
        print("none" if args.all else "none is new")
    else:
        print("\n".join(one.line() for one in shown))
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="every record, the marked ones too")
    parser.add_argument("--json", action="store_true", help="the records as JSON")
    parser.add_argument(
        "--for",
        dest="listed",
        default="",
        metavar="HOME",
        help="the records another home kept for this home, root or a scope",
    )
    marks = parser.add_subparsers(dest="verb")
    take = marks.add_parser("take", help="mark one taken by a queue row or a plan entry")
    take.add_argument("key")
    take.add_argument("--row", required=True, metavar="SLUG")
    drop = marks.add_parser("drop", help="mark one dropped, and say why")
    drop.add_argument("key")
    drop.add_argument("--why", required=True)
    for one in (take, drop):
        one.add_argument("--by", required=True)
        one.add_argument("--at", required=True, help="as queue remove takes it")
    add = marks.add_parser("add", help="keep one record for another home of the project")
    add.add_argument("--for", dest="home", required=True, metavar="HOME", help="root or a scope")
    add.add_argument(
        "--from", dest="sender", required=True, metavar="THREAD", help="this home's own thread"
    )
    add.add_argument("text", nargs="+")


VERBS = (
    verbs.Verb(
        "noticed",
        "the Noticed lines and the records for a home: the new ones, add one, take or drop one",
        _arguments,
        _noticed,
    ),
)


def _wake(half: Half) -> None:
    wake(half.run, half.client)


STEPS = (
    verbs.Step("tellers", 15, "noticed.scan", lambda half: scan(half.run), ("sight",)),
    verbs.Step("close", 90, "noticed.wake", _wake, ("sight", "client")),
)
