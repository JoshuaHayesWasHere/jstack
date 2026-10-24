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

A project's first pass finds no file. It marks every line that exists then as `dropped`, with the
why `FROM_BEFORE` and with `by` set to jbus. jbus does not count a line as new when the threads
wrote it before jbus kept the list. jbus writes nothing into a brief, asks nobody about a line and
makes no queue row for one. When the file does not parse, every verb that would write it refuses
(`Unparsable`), and a pass says so and leaves the file as it is.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import jbus
import jsettings
from jbus import mirror, plan, queue, verbs, write_json
from jbus.passes import Pass

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

    def line(self) -> str:
        """Return the record as one line: its key, where it is from, its mark, and its text."""
        said = {TAKEN: f" by {self.row}", DROPPED: f": {self.why}"}.get(self.mark, "")
        text = " ".join(self.text.split())
        return f"{self.key} {self.slug}, {self.section}, {self.mark}{said}: {text}"


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
    seen = now.astimezone(UTC).isoformat(timespec="seconds")
    for kind in ("tasks", "scouts"):
        for path in sorted((home / kind).glob("*.md")):
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for heading, body in mirror.sections(text, gates_inside=True):
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


@contextmanager
def _locked(state: Path) -> Iterator[None]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "noticed.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read(state: Path) -> list[Record] | None:
    """Return every record as the file keeps it, or None where there is no file yet. Raise
    `Unparsable` when the file is not in the form this module writes."""
    file = path(state)
    if not file.exists():
        return None
    try:
        kept = json.loads(file.read_text())
        records = [Record(**one) for one in kept["records"]]
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise Unparsable(f"refused: {file} does not parse, and nothing writes it") from error
    if any(one.mark not in MARKS for one in records):
        raise Unparsable(f"refused: {file} has a mark that is not one of {', '.join(MARKS)}")
    return records


def _write(state: Path, records: list[Record]) -> None:
    write_json(path(state), {"records": [asdict(one) for one in records]})


def keep(state: Path, home: Path, now: datetime, *, before: frozenset[str] = frozenset()) -> int:
    """Add what is new, and return how many records this function added. On the first pass it adds
    every line that exists, marked dropped with the why `FROM_BEFORE`. It does the same for every
    line of the files `before` names, which look like `tasks/<slug>.md` or `scouts/<slug>.md`: the
    ones `mirror.scan` found restored."""
    with _locked(state):
        records = read(state)
        first = records is None
        records = records or []
        known = {one.key for one in records}
        stamp = now.astimezone(UTC).isoformat(timespec="seconds")
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
    with _locked(state):
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


def _noticed(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state, home = config.state(project), config.home(project)
    if args.verb == "take":
        print(mark(state, home, args.key, args.by, args.at, config.user, row=args.row))
        return 0
    if args.verb == "drop":
        print(mark(state, home, args.key, args.by, args.at, config.user, why=args.why))
        return 0
    records = read(state)
    if records is None:
        print("none: no pass has read the Noticed lines yet")
        return 0
    shown = [one for one in records if args.all or one.mark == NEW]
    shown.sort(key=lambda one: (one.seen_at, one.key), reverse=True)
    if args.json:
        print(json.dumps([asdict(one) for one in shown], indent=2))
    elif not shown:
        print("none" if args.all else "none is new")
    else:
        print("\n".join(one.line() for one in shown))
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="every record, the marked ones too")
    parser.add_argument("--json", action="store_true", help="the records as JSON")
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


VERBS = (
    verbs.Verb(
        "noticed", "the Noticed lines: the new ones, and take or drop one", _arguments, _noticed
    ),
)
STEPS = (verbs.Step("tellers", 15, "noticed.scan", lambda half: scan(half.run), ("sight",)),)
