"""The queue table: one row per brief, in `queue.json` under the project's state directory.

A row has two kinds of column, with one writer each. The Chef's columns are written only
by the verbs here: `add`, `approve`, `hold` and `remove`. The derived columns are written
only by a pass, from what T3 Code and GitHub say (`derive`), and no verb takes one. Two of
them are a pair: `why` is the reason a row waits, and `since` is when that reason first held. Each
change of a row's status is also kept, one line each, in `transitions.jsonl` beside the
table, which is only ever appended to. `add` refuses a brief that a launch would refuse
(`jbriefs.parse.faults`), so no brief that cannot launch is put to the user for a go. The
brief a row was added with is kept beside the table, in `briefs/<slug>.md`, and `approve`
records its sha256 and its meaning fingerprint (`jbriefs.meaning`): the go holds for a
brief that asks for the same, whatever its wording, and not for one whose scope changed.
`approve` is also given the sha of the brief the user was shown, and is refused when the
stored brief is another.

An approval rests on words of the user's that something else holds, and `approve` names
them: a word `jbus word` kept, the answer that closed a question, a message of a T3 Code
thread, or a pick he sent from a Lavish page (`PAGE`), read from Lavish's own state file.
It takes no name and no time. The row's `approval` is the record (`Approval`): the
basis and its reference, the words, when and where they were said, whether it was T3 Code
or Lavish that jbus read them out of, and who ran the command and when, which jbus writes.
`approved` holds the line that says so, and is what every reader asks to know whether the
row has a go. An older row holds only a typed string there, and still has its go (`approval`).

One more basis is not his word for the row: a home approves a follow-up by a standing rule
(`RULE`), and names the parent row the user did give his word for (`follows`). The words
kept are the rule's, as the home's `standing.md` had it then (`rule`). The parent's own
approval is by one of the other bases or the typed string, so a chain is one step
(`_parent`), and the row's line says he did not speak of it. A `hold` of the parent, or a
`remove` of one that did not merge, takes the go of its queued follow-ups back with it.

The sha of a brief is `brief_sha`. It leaves out the `Home:` and `Thread:` lines of the
brief's head, which say whom the brief is sent to and not what it asks for: `Thread:` is
written in after a launch, and a brief queued again under another home is the same brief.
The stored brief is kept whole, those lines included, and a launch sends it without them
(`body`). A row approved before the fingerprint holds its go for the text it was given
on: its `brief_sha`, or for one approved before the sha left the two lines out, the
sha256 of the whole text. `approved_text` still takes both, and an `add` of such a row
turns the second into the `brief_sha` of the text it was approved with.

`remove` takes a row out for good. The slug is then in `removed.json` beside the table,
with who said so and when, and that file is how a pass decides a slug is gone: it sends no
finding for a slug the file names, and tells no thread of it to carry on. The file is
written before the table, and `load` gives no row of a slug it names, so a removal that
died between the two is a removal. The row as it was is one line of `transitions.jsonl`,
and the stored brief is moved to `removed/<slug>.<the first 12 of its sha>.md`. A slug
the file names is not added again. A `removed.json` that does not parse is `Unparsable`
as the table is: nothing is launched and no verb writes until it is mended.

`entry` is the Chef's column that only `add` writes: the slug of the plan entry the row is
work for, where that is not the row's own slug. An entry is often several briefs, and
`jbus plan` counts an entry's status from the rows that name it (`jbus.plan`). A row that
holds none is its own entry (`entry`).

`item` is the other column only `add` writes: the id of the work item the row is
(`jbus.item`). Once a row has one, an `add` that names another is refused.

The verbs are run as a batch, every one or none (`apply`): each is done to the table and
the briefs in memory, and the files are written once the last one is done. A verb typed
alone is a batch of one.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import meaning
from jbriefs import parse as briefs
from jbus import Refused, write_json

EVENTS = {"queue": "quiet"}
CHEF = ("slug", "priority", "depends", "approved", "brief_sha", "entry")
SEEN = ("status", "thread", "pr", "checks")
DERIVED = (*SEEN, "updated", "why", "since")
STATUSES = (
    "queued",
    "launched",
    "running",
    "waiting",
    "pr",
    "merged",
    "failed",
    "stale",
    "gate",
    "done",
    "left",
)
FINAL = ("merged", "done")
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
_SENT_TO = ("Home:", "Thread:")
PAGE = "page"
BASES = ("word", "answer", "message", PAGE)
BASIS = (
    "--word <id>, --answer <number>, --message <thread id>/<message id> or --page "
    "<session key>/<entry id>"
)
RULE = "rule"
BY_RULE = "--rule <n> with --follows <parent slug>"
FOLLOWED = "a follow-up approved by rule has no go without its parent's"
SESSION = "CLAUDE_CODE_SESSION_ID"
GO_HOLDS = ", its go holds"
GO_VOID = ", its go does not hold for it: approve it again"

Row = dict[str, Any]


class Unparsable(Exception):
    """`queue.json` is there and is not a list of rows, or `removed.json` is there and is not
    a table of slugs. `path` is the file."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} does not parse")
        self.path = path


def path(state: Path) -> Path:
    return state / "queue.json"


def transitions_path(state: Path) -> Path:
    return state / "transitions.jsonl"


def brief_path(state: Path, slug: str) -> Path:
    return state / "briefs" / f"{slug}.md"


def removed_path(state: Path) -> Path:
    return state / "removed.json"


def aside_path(state: Path, slug: str, text: str) -> Path:
    """Where the stored brief of a removed row is kept."""
    return state / "removed" / f"{slug}.{brief_sha(text)[:12]}.md"


def removed(state: Path) -> dict[str, dict[str, str]]:
    """The slugs that were removed for good, each with `at` and `by` as `remove` was given."""
    try:
        text = removed_path(state).read_text()
    except (FileNotFoundError, NotADirectoryError):
        return {}
    try:
        kept = json.loads(text)
        if not isinstance(kept, dict) or not all(isinstance(one, dict) for one in kept.values()):
            raise ValueError
    except ValueError as error:
        raise Unparsable(removed_path(state)) from error
    return kept


def removed_slugs(state: Path) -> frozenset[str]:
    """The removed slugs, for what only leaves them out. Where the file does not parse it
    names none: `load` is what says so, and a pass then sends a gate for the file."""
    try:
        return frozenset(removed(state))
    except Unparsable:
        return frozenset()


def clock() -> datetime:
    """The time an approval is run at, and a removal's line of `transitions.jsonl` is written
    with."""
    return datetime.now(UTC)


def runner() -> dict[str, str]:
    """Who runs the command: the session the environment names, and the directory."""
    return {"session": os.environ.get(SESSION, ""), "directory": str(Path.cwd())}


def who(ran_by: dict[str, str]) -> str:
    """Who ran a command, as `runner` found it: the home of the directory it was run in, or a
    shell where no session ran it."""
    directory = ran_by.get("directory", "")
    if not ran_by.get("session"):
        return f"a shell in {directory}"
    return f"the {Path(directory).name} home"


@dataclass(frozen=True)
class Said:
    """Words of the user's as whatever keeps them has them: when and where they were said,
    and whether jbus read the words and the time from T3 Code or Lavish (`checked`) or was
    typed them. `ref` is the `<thread id>/<message id>` or `<session key>/<entry id>` they were
    read from, or nothing."""

    words: str
    said_at: str
    said_in: str
    checked: bool
    ref: str = ""


@dataclass(frozen=True)
class Approval:
    """A row's go. `basis` is one of `BASES` and `ref` names the record of it: a word's id, a
    question's number, `<thread id>/<message id>`, or for `PAGE` `<session key>/<entry id>`,
    whose `said_in` is the page's file. `ran_by` is `runner` and `ran_at` the
    clock, both as jbus found them: no option gives either.

    With the basis `RULE`, `ref` is the rule's number, `words` the rule's text and `follows`
    the slug of the parent row. The user said nothing of the row, so `said_at` and `said_in`
    are empty. No other basis has a `follows`, and its record keeps none.

    `brief_sha` is the stored brief's at the go, `meaning` its fingerprint and `scope` the
    sha256 of that (`jbriefs.meaning`): the go holds for a brief that means the same. An older
    record, made before the fingerprint, has none of the three, and its row's `brief_sha` is
    the go's."""

    basis: str
    ref: str
    words: str
    said_at: str
    said_in: str
    checked: bool
    ran_by: dict[str, str]
    ran_at: str
    follows: str = ""
    brief_sha: str = ""
    scope: str = ""
    meaning: list[Any] = field(default_factory=list)

    def who(self) -> str:
        return who(self.ran_by)

    def line(self) -> str:
        if self.basis == RULE:
            parent = f"rule {self.ref}, follow-up of {self.follows}"
            return f"{parent}; run {self.ran_at} by {self.who()}; he did not speak of this row"
        ran = f"run {self.ran_at} by {self.who()}"
        if self.basis == PAGE:
            return f"his pick on a Lavish page, {self.said_at}, {Path(self.said_in).name}; {ran}"
        typed = "" if self.checked else " (time typed)"
        where = f", in {self.said_in}" if self.said_in else ""
        return f"his word, {self.said_at}{typed}{where}; {ran}"


def record(row: Row) -> Approval | None:
    """The row's approval as a record, or None for a row with none or with a typed string."""
    try:
        return Approval(**row["approval"]) if row.get("approval") else None
    except TypeError:
        return None


def approval(row: Row) -> str:
    """What is said of a row's go: the record's line, the typed string of a row from before
    with what it is, or nothing for a row with no go."""
    kept, typed = record(row), row.get("approved", "")
    if kept:
        return kept.line()
    return f"{typed} (typed, not checked)" if typed else ""


def held(made: Approval) -> dict[str, Any]:
    """The record as a row holds it: with `follows` only where the approval has a parent."""
    return {name: value for name, value in asdict(made).items() if name != "follows" or value}


_NUMBERED = re.compile(r"\d+\. ")


def rule(standing: Path, number: str) -> Said:
    """Rule `number` of a home's standing rules, as the file has it now: the line that starts
    `<number>. `, up to the next numbered line or heading. jbus reads it and never writes it."""
    if not number.isdecimal():
        raise Refused(f"refused: --rule is a rule's number, not {number}")
    try:
        lines = standing.read_text().splitlines()
    except OSError:
        lines = []
    found: list[str] | None = None
    for line in lines:
        if found is None:
            if line.startswith(f"{number}. "):
                found = [line.removeprefix(f"{number}. ")]
        elif line.startswith("#") or _NUMBERED.match(line):
            break
        else:
            found.append(line)
    words = "\n".join(found or []).strip()
    if not words:
        raise Refused(f"refused: {standing} has no rule {number}")
    return Said(words, "", "", True)


def ran_at(row: Row) -> str:
    """When the row's approval was run, by its record. A typed string gives no time."""
    kept = record(row)
    return kept.ran_at if kept else ""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def body(text: str) -> str:
    """The brief with no `Home:` and no `Thread:` line in its head, the lines above its first
    `## `. They name the threads the brief is sent to, and a brief is the same brief under
    another home. It is what a launch sends, so no line goes out that the sha leaves out."""
    kept, head = [], True
    for line in text.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(_SENT_TO)):
            kept.append(line)
    return "".join(kept)


def brief_sha(text: str) -> str:
    """The sha256 a brief is approved by, shown by and launched by: that of its `body`."""
    return sha(body(text))


def fingerprint(text: str) -> meaning.Meaning:
    """What the brief asks for, its `Home:` and `Thread:` lines left out (`jbriefs.meaning`)."""
    return meaning.meaning(body(text))


def approved_text(row: Row, text: str) -> bool:
    """Whether `text` is a brief the row's go holds for.

    A go recorded with a fingerprint holds for every brief that means the same
    (`meaning.same`), whatever its wording. One from before holds for the text it was given
    on: its row's `brief_sha`, or for a row approved before the sha left the two lines out,
    the sha256 of the whole text, line for line.
    """
    kept = record(row)
    if kept and kept.scope:
        return meaning.same(kept.meaning, fingerprint(text))
    return row.get("brief_sha") in (brief_sha(text), sha(text))


def verify(row: Row, text: str | None, path: str) -> dict[str, Any]:
    """What another reader needs to check a go: the row's record, and the brief at `path`
    with its sha, its fingerprint and whether the go holds for it."""
    kept = record(row)
    made = held(kept) if kept else {}
    now = {"path": path, "brief_sha": "", "scope": "", "meaning": []}
    if text is not None:
        mine = fingerprint(text)
        now.update(brief_sha=brief_sha(text), scope=meaning.fingerprint(mine), meaning=mine)
    return {
        "slug": row["slug"],
        "approved": approval(row),
        "holds": bool(row.get("approved")) and text is not None and approved_text(row, text),
        "brief_sha": row.get("brief_sha", ""),
        "approval": made,
        "brief": now,
    }


def brief(state: Path, slug: str) -> str | None:
    try:
        return brief_path(state, slug).read_text()
    except OSError:
        return None


def _well_formed(row: Any) -> bool:
    """A row whose Chef columns have the types every pass sorts and compares by."""
    return (
        isinstance(row, dict)
        and isinstance(row.get("slug"), str)
        and type(row.get("priority", 0)) is int
        and isinstance(row.get("depends", []), list)
        and all(isinstance(slug, str) for slug in row.get("depends", []))
        and isinstance(row.get("entry", ""), str)
        and isinstance(row.get("approved", ""), str)
        and isinstance(row.get("approval", {}), dict)
        and isinstance(row.get("brief_sha", ""), str)
        and isinstance(row.get("item", ""), str)
    )


def fresh(state: Path, slug: str) -> Row | None:
    """The row as it is now, read under the lock the verbs write under."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "queue.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return next((row for row in load(state) if row["slug"] == slug), None)
        except Unparsable:
            return None


def load(state: Path) -> list[Row]:
    """The rows of the table, but for a row of a slug that `removed.json` names."""
    gone = removed(state)
    try:
        text = path(state).read_text()
    except FileNotFoundError:
        return []
    try:
        rows = json.loads(text)
        if not isinstance(rows, list) or not all(_well_formed(row) for row in rows):
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise Unparsable(path(state)) from error
    return [row for row in rows if row["slug"] not in gone]


@contextmanager
def _changing(state: Path) -> Iterator[list[Row]]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "queue.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            rows = load(state)
        except Unparsable as error:
            raise Refused(f"refused: {error}, and nothing writes it") from error
        before = json.dumps(rows, sort_keys=True)
        yield rows
        rows.sort(key=order)
        if json.dumps(rows, sort_keys=True) != before:
            write_json(path(state), rows)


def over(row: Row) -> bool:
    """A row that is finished and leaves nothing: merged or done, with no reason to wait."""
    return row.get("status") in FINAL and not row.get("why")


def entry(row: Row) -> str:
    """The plan entry the row is work for: the one `add` was given, or the row's own slug."""
    return row.get("entry") or row["slug"]


def order(row: Row) -> tuple[int, str]:
    return (row.get("priority", 0), row["slug"])


def _was(slug: str, gone: dict[str, dict[str, str]]) -> str:
    return f"{slug} was removed {gone[slug].get('at', '')} by {gone[slug].get('by', '')}"


def was_removed(state: Path, slug: str) -> str:
    """The line that says who removed the slug and when, or nothing for one that was not."""
    try:
        gone = removed(state)
    except Unparsable:
        return ""
    return _was(slug, gone) if slug in gone else ""


def _row(rows: list[Row], slug: str, gone: dict[str, dict[str, str]]) -> Row:
    for row in rows:
        if row["slug"] == slug:
            return row
    said = f": {_was(slug, gone)}" if slug in gone else ""
    raise Refused(f"refused: the queue has no row {slug}{said}")


@dataclass(frozen=True)
class Add:
    """A new row, or a row's brief, priority and depends again. Its approval is left as it
    is, and so is its entry where `entry` is empty. An `entry` that is the row's own slug
    takes the row's entry away: the row is then its own entry, and holds none."""

    slug: str
    priority: int
    depends: list[str]
    text: str
    entry: str = ""
    item: str = ""


@dataclass(frozen=True)
class Approve:
    """The user's go for the brief whose sha256 starts with `given`, by the words `ref` names.
    By a rule, `ref` is the rule's number and `follows` the parent row's slug."""

    slug: str
    basis: str
    ref: str
    given: str
    follows: str = ""


@dataclass(frozen=True)
class Hold:
    slug: str


@dataclass(frozen=True)
class Remove:
    """The user's word that the row goes for good."""

    slug: str
    by: str
    at: str


Verb = Add | Approve | Hold | Remove


@dataclass(frozen=True)
class Asks:
    """What a `remove` and an `approve` ask of the world outside the table.

    `out` says what of a slug is out, in one line, or nothing. It may take seconds, so it is
    asked before the table is locked. `launched` is asked with the table locked, and says
    whether a launch of the slug is under way or was made since `out` was asked. `told` is
    given each removal's line of `transitions.jsonl`, once `removed.json` names the slug.
    `said` is given an approval's basis and reference and gives the user's words they name,
    or the text of the standing rule, or refuses. It may ask T3 Code, so it too is asked
    before the table is locked.
    """

    out: Callable[[str], str]
    launched: Callable[[str], str]
    told: Callable[[dict[str, Any]], None]
    said: Callable[[str, str], Said] | None = None


_OPTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "add": (("priority",), ("depends", "entry")),
    "approve": (("sha",), (*BASES, RULE, "follows", "by", "at")),
    "hold": ((), ()),
    "remove": (("by", "at"), ()),
}
_BRIEF, _END = "--- brief ", "--- end"


def basis(given: Mapping[str, Any]) -> tuple[str, str, str]:
    """The one basis an `approve` was given, its reference, and the parent a rule's follow-up
    names. None, more than one, a rule with no parent, a parent with no rule, or a name or a
    time beside it, is refused."""
    named = [
        (name, str(given[name])) for name in (*BASES, RULE) if given.get(name) not in (None, "")
    ]
    follows = str(given.get("follows") or "")
    by_rule = [name for name, _ in named] == [RULE]
    stamped = any(given.get(name) is not None for name in ("by", "at"))
    if len(named) != 1 or by_rule != bool(follows) or stamped:
        raise Refused(
            f"refused: approve takes one basis, {BASIS}, or {BY_RULE}, and no --by and no "
            "--at: jbus writes who ran it and when"
        )
    return (*named[0], follows)


def slugs(text: str) -> list[str]:
    return [slug for slug in text.split(",") if slug]


@dataclass
class _Batch:
    """What a batch has done so far, in memory: nothing is on disk until its last verb is."""

    state: Path
    rows: list[Row]
    gone: dict[str, dict[str, str]]
    briefs: dict[str, str | None]
    moves: list[dict[str, Any]]
    aside: dict[Path, str]

    def brief(self, slug: str) -> str | None:
        return self.briefs[slug] if slug in self.briefs else brief(self.state, slug)

    def row(self, slug: str) -> Row:
        return _row(self.rows, slug, self.gone)


def _went(batch: _Batch, slug: str) -> Row | None:
    """The row of a removed slug as it was when it went: by this batch, or by the last line
    of `transitions.jsonl` that removed it."""
    try:
        lines = transitions_path(batch.state).read_text().splitlines()
    except OSError:
        lines = []
    moves = []
    for line in lines:
        try:
            moves.append(json.loads(line))
        except ValueError:
            continue
    for move in (*reversed(batch.moves), *reversed(moves)):
        if isinstance(move, dict) and move.get("slug") == slug and move.get("to") == "removed":
            return move["row"] if isinstance(move.get("row"), dict) else None
    return None


def _parent(batch: _Batch, slug: str, follows: str) -> None:
    """Refuse a follow-up whose parent is not a row the user gave his own word for.

    The parent is a row of the table, or one that was removed after it merged. Its approval
    is a record by one of `BASES`, or the typed string of a row from before. A parent that
    was itself approved by a rule is refused, and so is a row that another row follows, whose
    own word a rule approval would write over: nothing is more than one step from his word.
    """
    cannot = f"refused: {slug} cannot follow"
    if follows == slug:
        raise Refused(f"{cannot} itself")
    behind = sorted(row["slug"] for row in batch.rows if (record(row) or Approval).follows == slug)
    if behind:
        raise Refused(
            f"{cannot} {follows}: {', '.join(behind)} follow {slug}, and a chain is one step: "
            f"take his word for {slug}"
        )
    row = next((row for row in batch.rows if row["slug"] == follows), None)
    here = row is not None
    if row is None:
        if follows not in batch.gone:
            raise Refused(f"{cannot} {follows}: the queue has no row {follows}")
        row = _went(batch, follows)
        if row is None or row.get("status") != "merged":
            was = _was(follows, batch.gone)
            raise Refused(f"{cannot} {follows}: {was}, and its row did not go as merged")
    made = record(row)
    if made and made.basis == RULE:
        raise Refused(
            f"{cannot} {follows}: {follows} was approved by rule {made.ref} as a follow-up of "
            f"{made.follows}, and a chain is one step: follow {made.follows}, or take his word "
            f"for {slug}"
        )
    if not row.get("approved"):
        raise Refused(f"{cannot} {follows}: {follows} has no approval")
    text = batch.brief(follows) if here else None
    if text is not None and not approved_text(row, text):
        raise Refused(f"{cannot} {follows}: {follows}'s brief changed after its approval")


def _hold(row: Row) -> None:
    row.update(approved="", brief_sha="")
    row.pop("approval", None)


def _unfollow(rows: list[Row], parent: str) -> list[str]:
    """Take the go back from each row approved as a follow-up of `parent` that is still
    queued: its go rested on the parent's, which is gone. The answer is their slugs. A row
    that was launched keeps its record, since nothing takes a launch back."""
    held = []
    for row in rows:
        made = record(row)
        if made and made.follows == parent and row.get("status", "queued") == "queued":
            _hold(row)
            held.append(row["slug"])
    return sorted(held)


def _do(
    verb: Verb,
    batch: _Batch,
    user: jsettings.Settings | None,
    asks: Asks | None,
    out: dict[str, str | Refused],
    said: dict[tuple[str, str], Said | Refused],
) -> str:
    rows = batch.rows
    if isinstance(verb, Hold):
        _hold(batch.row(verb.slug))
        also = _unfollow(rows, verb.slug)
        return f"held {verb.slug}" + (
            f", and {', '.join(also)} with it: {FOLLOWED}" if also else ""
        )
    if isinstance(verb, Add):
        if not _SLUG.fullmatch(verb.slug):
            raise Refused(f"refused: {verb.slug} is not a slug")
        if verb.slug in batch.gone:
            said = _was(verb.slug, batch.gone)
            raise Refused(f"refused: {said}, and a removed slug is not added again")
        for other in verb.depends:
            if other in batch.gone:
                said = _was(other, batch.gone)
                raise Refused(f"refused: {verb.slug} cannot depend on {other}: {said}")
        if verb.entry and not _SLUG.fullmatch(verb.entry):
            raise Refused(f"refused: --entry is a plan entry's slug, not {verb.entry}")
        if not verb.text.strip():
            raise Refused("refused: no brief on stdin")
        faults = briefs.faults(body(verb.text))
        if faults:
            many = "1 fault" if len(faults) == 1 else f"{len(faults)} faults"
            lines = "".join(f"\n- {fault}" for fault in faults)
            raise Refused(f"refused: {verb.slug}'s brief has {many}, and nothing is queued{lines}")
        found = [row for row in rows if row["slug"] == verb.slug]
        row = (
            found[0] if found else {"slug": verb.slug, "approved": "", "brief_sha": "", **_blank()}
        )
        if verb.item and row.get("item", verb.item) != verb.item:
            raise Refused(f"refused: {verb.slug} is linked to {row['item']}, not {verb.item}")
        row.update(priority=verb.priority, depends=verb.depends)
        if verb.item:
            row["item"] = verb.item
        if verb.entry == verb.slug:
            row.pop("entry", None)
        elif verb.entry:
            row["entry"] = verb.entry
        was = batch.brief(verb.slug)
        kept = record(row)
        if was is not None and not (kept and kept.scope) and approved_text(row, was):
            row["brief_sha"] = brief_sha(was)
        if not found:
            rows.append(row)
        batch.briefs[verb.slug] = verb.text
        depends = f", depends {', '.join(verb.depends)}" if verb.depends else ""
        of = f", entry {row['entry']}" if "entry" in row else ""
        shown = brief_sha(verb.text)[:12]
        go = ""
        if row.get("approved") and was is not None and brief_sha(was) != brief_sha(verb.text):
            holds = approved_text(row, verb.text)
            go = GO_HOLDS if holds else GO_VOID
        return f"added {verb.slug}: priority {verb.priority}{depends}{of}, brief {shown}{go}"
    if isinstance(verb, Approve):
        if user is None or (verb.basis, verb.ref) not in said:
            raise Refused("refused: approve was given nothing to read the user's word with")
        row = batch.row(verb.slug)
        text = batch.brief(verb.slug)
        if text is None:
            raise Refused(f"refused: {verb.slug} has no brief, add it again")
        stored = brief_sha(text)
        if stored[:12] != verb.given:
            raise Refused(f"refused: {verb.slug}'s brief is {stored[:12]}, not {verb.given}")
        rests = said[verb.basis, verb.ref]
        if isinstance(rests, Refused):
            raise rests
        if verb.basis == RULE:
            _parent(batch, verb.slug, verb.follows)
        means = fingerprint(text)
        made = Approval(
            basis=verb.basis,
            ref=verb.ref,
            words=rests.words,
            said_at=rests.said_at,
            said_in=rests.said_in,
            checked=rests.checked,
            ran_by=runner(),
            ran_at=user.stamp(clock()),
            follows=verb.follows,
            brief_sha=stored,
            scope=meaning.fingerprint(means),
            meaning=means,
        )
        row.update(approved=made.line(), approval=held(made), brief_sha=stored)
        return f"approved {verb.slug}: brief {stored[:12]}, {made.line()}"
    if user is None:
        raise Refused("refused: remove was given no settings to check --by and --at with")
    if verb.by != user.user:
        raise Refused(f"refused: only {user.user} removes a row, not {verb.by}")
    if not user.takes(verb.at):
        raise Refused(f'refused: --at is "{user.form(verb.at)}"')
    row = batch.row(verb.slug)
    text = batch.brief(verb.slug)
    waits = sorted(
        other["slug"]
        for other in rows
        if verb.slug in other.get("depends", []) and other.get("status") != "merged"
    )
    if waits:
        raise Refused(f"refused: {', '.join(waits)} wait on {verb.slug}: remove them first")
    if asks is None:
        raise Refused("refused: remove was given nothing to ask what is out with")
    is_out = out[verb.slug]
    if isinstance(is_out, Refused):
        raise is_out
    is_out = is_out or asks.launched(verb.slug)
    if is_out:
        raise Refused(f"refused: {is_out}")
    kept = None
    if text is not None:
        kept = aside_path(batch.state, verb.slug, text)
        batch.aside[kept] = text
    was = row.get("status", "queued")
    batch.moves.append(
        {
            "slug": verb.slug,
            "from": was,
            "to": "removed",
            "at": clock().astimezone(UTC).isoformat(timespec="seconds"),
            "by": verb.by,
            "said": verb.at,
            "row": dict(row),
            "brief": str(kept) if kept else "",
        }
    )
    rows.remove(row)
    batch.gone[verb.slug] = {"at": verb.at, "by": verb.by}
    batch.briefs[verb.slug] = None
    where = f"brief kept at {kept}" if kept else "it had no stored brief"
    also = [] if was == "merged" else _unfollow(rows, verb.slug)
    more = f", and held {', '.join(also)}: {FOLLOWED}" if also else ""
    return f"removed {verb.slug}: was {was}, {verb.at} by {verb.by}, {where}{more}"


def _none(line: int, error: Exception) -> Refused:
    said, *more = str(error).removeprefix("refused: ").split("\n")
    lines = "".join(f"\n{one}" for one in more)
    return Refused(f"refused: line {line}: {said}, and nothing in the batch was applied{lines}")


def _run(
    state: Path,
    verbs: list[tuple[int, Verb]],
    user: jsettings.Settings | None = None,
    asks: Asks | None = None,
) -> list[str]:
    """Every verb or none. A verb numbered 0 was typed alone, and is refused in its own words.

    `user` is whom a `remove` is checked against and whose zone an approval's time is
    written in: `add` and `hold` read no settings. `asks` is what a `remove` and an `approve`
    ask: a batch with either needs it.

    A removal is done once `removed.json` names its slug: `load` gives no row of it from
    then on. The brief's copy aside and the line of `transitions.jsonl` are written before
    that, so the line names a file that is there, and a batch that dies before
    `removed.json` is written writes both again when it is run again: the copy is named by
    its sha, so twice is once. What comes after is the stored brief taken away, the event
    and the table. A batch that dies there leaves a removal with a brief still stored or no
    event, and neither brings the row back.
    """
    said = []
    out: dict[str, str | Refused] = {}
    for _, verb in verbs:
        if asks is not None and isinstance(verb, Remove) and verb.slug not in out:
            try:
                out[verb.slug] = asks.out(verb.slug)
            except Refused as error:
                out[verb.slug] = error
    said_by: dict[tuple[str, str], Said | Refused] = {}
    for _, verb in verbs:
        named = (verb.basis, verb.ref) if isinstance(verb, Approve) else None
        if asks is not None and asks.said is not None and named and named not in said_by:
            try:
                said_by[named] = asks.said(*named)
            except Refused as error:
                said_by[named] = error
    moves: list[dict[str, Any]] = []
    with _changing(state) as rows:
        try:
            gone = removed(state)
        except Unparsable as error:
            raise Refused(f"refused: {error}, and nothing writes it") from error
        batch = _Batch(state, rows, gone, {}, moves, {})
        for line, verb in verbs:
            try:
                said.append(_do(verb, batch, user, asks, out, said_by))
            except Refused as error:
                if not line:
                    raise
                raise _none(line, error) from error
        for kept, text in batch.aside.items():
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_text(text)
        if batch.moves:
            with open(transitions_path(state), "a") as log:
                log.writelines(json.dumps(move) + "\n" for move in batch.moves)
            write_json(removed_path(state), batch.gone)
        for slug, text in batch.briefs.items():
            if text is None:
                brief_path(state, slug).unlink(missing_ok=True)
            else:
                brief_path(state, slug).parent.mkdir(parents=True, exist_ok=True)
                brief_path(state, slug).write_text(text)
        for move in moves if asks else []:
            asks.told(move)
    return said


def add(
    state: Path,
    slug: str,
    priority: int,
    depends: list[str],
    text: str,
    entry: str = "",
    item: str = "",
) -> str:
    """Add the row, or its brief again, linked to the work item `item` where that is given.
    The answer is the line that says what was added."""
    return _run(state, [(0, Add(slug, priority, depends, text, entry, item))])[0]


def approve(
    state: Path,
    slug: str,
    rests: tuple[str, str, str],
    given: str,
    user: jsettings.Settings,
    asks: Asks,
) -> None:
    """Record the go. `rests` is the basis, its reference and the parent, as `basis` gives
    them."""
    kind, ref, follows = rests
    _run(state, [(0, Approve(slug, kind, ref, given, follows))], user, asks)


def hold(state: Path, slug: str) -> str:
    """Take the row's go back. The answer is the line that says what was held."""
    return _run(state, [(0, Hold(slug))])[0]


def remove(state: Path, slug: str, by: str, at: str, user: jsettings.Settings, asks: Asks) -> str:
    """Take the row out for good. The answer is the line that says what was done."""
    return _run(state, [(0, Remove(slug, by, at))], user, asks)[0]


def _options(verb: str, words: list[str]) -> dict[str, str]:
    needed, allowed = _OPTIONS[verb]
    given: dict[str, str] = {}
    rest = iter(words)
    for word in rest:
        name, joined, value = word.removeprefix("--").partition("=")
        if name.replace("-", "_") in DERIVED:
            column = name.replace("-", "_")
            raise Refused(
                f"refused: {column} is derived from T3 Code and GitHub, and no command writes it"
            )
        if not word.startswith("--") or name not in (*needed, *allowed):
            raise Refused(f"refused: {verb} takes no {word.partition('=')[0]}")
        if not joined:
            value = next(rest, "")
        given[name] = value
    for name in needed:
        if name not in given:
            raise Refused(f"refused: {verb} needs --{name}")
    return given


def parse(text: str) -> list[tuple[int, Verb]]:
    """A batch as its verbs, each with the number of the line it is on.

    A line is `add <slug> --priority N [--depends a,b] [--entry <plan entry>]`, `approve
    <slug> --sha <12>` with one of `--word <id>`, `--answer <number>`, `--message
    <thread id>/<message id>` and `--page <session key>/<entry id>`, or with `--rule <n>
    --follows <parent slug>`, `hold <slug>` or `remove <slug> --by <user> --at "<YYYY-MM-DD
    HH:MM ZONE>"`. Under an `add` comes its brief, between a line `--- brief <slug>` and a
    line `--- end`: the lines between are the brief, as they are, so a brief cannot hold
    either marker as a line of its own.
    """
    lines = text.splitlines(keepends=True)
    verbs: list[tuple[int, Verb]] = []
    at = 0
    while at < len(lines):
        number, line = at + 1, lines[at]
        at += 1
        try:
            words = shlex.split(line)
            if not words:
                continue
            verb, slug = words[0], words[1] if len(words) > 1 else ""
            if verb not in _OPTIONS:
                raise Refused(f"refused: {verb} is not add, approve, hold or remove")
            if not slug or slug.startswith("--"):
                raise Refused(f"refused: {verb} needs a slug")
            given = _options(verb, words[2:])
            if verb == "hold":
                verbs.append((number, Hold(slug)))
            elif verb == "approve":
                kind, ref, follows = basis(given)
                verbs.append((number, Approve(slug, kind, ref, given["sha"], follows)))
            elif verb == "remove":
                verbs.append((number, Remove(slug, given["by"], given["at"])))
            else:
                try:
                    priority = int(given["priority"])
                except ValueError:
                    raise Refused(
                        f"refused: --priority is an integer, not {given['priority']}"
                    ) from None
                while at < len(lines) and not lines[at].strip():
                    at += 1
                if at == len(lines) or lines[at].rstrip() != f"{_BRIEF}{slug}":
                    raise Refused(f"refused: add {slug} has no {_BRIEF}{slug} line under it")
                end = at + 1
                while end < len(lines) and lines[end].rstrip() != _END:
                    end = len(lines) if lines[end].startswith(_BRIEF) else end + 1
                if end == len(lines):
                    raise Refused(f"refused: {slug}'s brief has no {_END} line")
                brief_text = "".join(lines[at + 1 : end])
                at = end + 1
                depends = slugs(given.get("depends", ""))
                of = given.get("entry", "")
                verbs.append((number, Add(slug, priority, depends, brief_text, of)))
        except (Refused, ValueError) as error:
            raise _none(number, error) from error
    if not verbs:
        raise Refused("refused: no verb on stdin")
    return verbs


def apply(state: Path, text: str, user: jsettings.Settings, asks: Asks) -> list[str]:
    return _run(state, parse(text), user, asks)


def _blank() -> Row:
    return {column: "queued" if column == "status" else "" for column in DERIVED}


@dataclass(frozen=True)
class Change:
    """A row one of whose columns in `SEEN` changed: the row as it is now, and each such
    column with what it held before and what it holds now."""

    row: Row
    columns: dict[str, tuple[str, str]]


def derive(
    state: Path, facts: Callable[[Row], Row], stamp: str, at: str
) -> tuple[list[Row], list[Change]]:
    """Rewrite every row's derived columns from `facts`. The answer says which rows changed.

    `updated` moves only with one of the columns in `SEEN`, so a quiet pass leaves the table
    as it was. `since` moves only with `why`, and is empty when there is no reason. Neither
    of the two counts as a change of the table.

    A status that changed is one line of `transitions.jsonl`: the slug, from, to, and `at`.
    The line is appended before the table is written, so a pass that dies between the two
    says a change twice and loses none.
    """
    changed = []
    moved = []
    with _changing(state) as rows:
        for row in rows:
            new = {**_blank(), **facts(row)}
            was = row.get("status", "queued")
            if was != new["status"]:
                moved.append({"slug": row["slug"], "from": was, "to": new["status"], "at": at})
            columns = {
                column: (row.get(column, ""), new[column])
                for column in SEEN
                if row.get(column, "") != new[column]
            }
            if columns:
                row.update({column: new[column] for column in SEEN}, updated=stamp)
                changed.append(Change(row, columns))
            if row.get("why", "") != new["why"]:
                row.update(why=new["why"], since=stamp if new["why"] else "")
        if moved:
            with open(transitions_path(state), "a") as log:
                log.writelines(json.dumps(move) + "\n" for move in moved)
    return rows, changed


def render(rows: list[Row]) -> str:
    columns = (*CHEF, *DERIVED)
    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    for row in sorted(rows, key=order):
        cells = []
        for column in columns:
            value = row.get(column, "")
            if column == "depends":
                value = ", ".join(value)
            elif column == "approved":
                value = approval(row)
            elif column == "brief_sha":
                value = str(value)[:12]
            cells.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def changes(changed: list[Change]) -> str:
    """What a pass changed: a line for each row, its columns as `from -> to`, then the table
    of those rows and of no other."""
    changed = sorted(changed, key=lambda change: order(change.row))
    said = []
    for change in changed:
        columns = (
            f"{column} {was or '(empty)'} -> {now or '(empty)'}"
            for column, (was, now) in change.columns.items()
        )
        said.append(f"{change.row['slug']}: {', '.join(columns)}\n")
    return "".join(said) + "\n" + render([change.row for change in changed])


def shown(rows: list[Row], every: bool = False) -> str:
    """The table of the rows still open, with a last line that counts the finished ones.

    With `every`, or with no row that is over, it is the whole table and no line more.
    """
    still = rows if every else [row for row in rows if not over(row)]
    left = len(rows) - len(still)
    if not left:
        return render(still)
    counted = "1 finished row" if left == 1 else f"{left} finished rows"
    return f"{render(still)}\n{counted} not shown: jbus queue show --all\n"
