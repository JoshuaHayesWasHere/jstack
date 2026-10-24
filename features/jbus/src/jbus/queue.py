"""The queue table has one row per brief, in `queue.json` under the project's state directory.

A row has two kinds of column, and each kind has one writer. Only the verbs here write the Chef's
columns: `add`, `approve`, `hold` and `remove`. Only a pass writes the derived columns, using what
T3 Code and GitHub say (`derive`), and no verb takes a derived column as input. Two derived columns
are a pair: `why` is the reason a row waits, and `since` is when that reason first held. jbus also
keeps each change of a row's status as one line of `transitions.jsonl` beside the table, and only
ever appends to that file.

When a row is first queued, `add` refuses a brief that a launch would refuse
(`jbriefs.parse.faults`), so nobody asks the user for a go on a brief that cannot launch. A
row with a go is grandfathered: a lint added after the go does not refuse its brief at an `add`
or at a launch. Only a fault that an edit brings refuses it. `show` names the grandfathered rows
(`grandfathered`).

jbus keeps the brief that came with a row's `add` beside the table, in `briefs/<slug>.md`, and
`approve` records the brief's sha256 and its meaning fingerprint (`jbriefs.meaning`). The go holds
for a brief whose title, Task, Done when, Where, Do not touch and Size are what they were, whatever
else changed, and not for one whose goal or scope changed. `approve` also takes the sha of the brief
the user was shown, and refuses when the stored brief differs from it.

An approval is based on the user's words, which another store holds, and `approve` names them: a
word that `jbus word` kept, the answer that closed a question, a message of a T3 Code thread, or a
pick the user sent with a Lavish page (`PAGE`), which jbus reads in Lavish's own state file.
`approve` takes no name and no time. The row's `approval` is the record (`Approval`). The record
holds the basis and its reference, the words, and when and where the user said them. It also says
whether jbus read the words out of T3 Code or Lavish, and who ran the command and when, which jbus
writes itself. `approved` holds a line that states the go, and every reader checks that column to
know whether the row has a go. An older row holds only a typed string there, and still has its go
(`approval`).

One more basis is not the user's word for the row: a home approves a follow-up by a standing rule
(`RULE`), and names the parent row that the user did give their word for (`follows`). The words jbus
keeps are the rule's text, as the home's `standing.md` had it then (`rule`). The parent's own
approval is by one of the other bases or the typed string, so a chain is one step long (`_parent`),
and the follow-up's line says that the user said nothing of the follow-up. A `hold` of the
parent, or a `remove` of a parent that did not merge, also takes back the go of the parent's queued
follow-ups.

jbus gives that go itself at the end of a batch (`_followers`, `_by_rule`), to a row that the
follow-up rule names a follow-up (`follow_up`, the rule in words is `FOLLOW_UP`): a row the batch
queued new, or queued again where its go was by rule, and a waiting row whose parent the batch
approved by the user's word. The rule's number is in the home's `follow-rule` file (`Asks.follow`),
and with none jbus approves no row by rule. So a follow-up is approved in the write that queues it,
and no pass lists it for the user.

`brief_sha` gives the sha of a brief. It leaves out the `Home:` and `Thread:` lines of the brief's
head, which say whom the brief is sent to and not what it asks for: a launch writes `Thread:` in,
and a brief queued again under another home is the same brief. jbus stores the brief whole, those
lines included, and a launch sends it without them (`body`). A row that the user approved before
jbus had the fingerprint (#249) holds its go for the text of that approval, which jbus matches by
the row's `brief_sha`, or, from before `brief_sha` left out the two lines, by the sha256 of the
whole text. The first `add` of such a row binds the go to the fingerprint of the stored brief, once,
while the go still holds for it: the row's `rebound` column. From then on the go holds as a
fingerprint's does, so a home that rewrites `Home:` or `Thread:` voids no older go.

When a go no longer holds, `changed` names the lines of the brief that differ from what was
approved (`meaning.changed`), and the pass's gate says them.

`remove` takes a row out for good. The slug then goes into `removed.json` beside the table,
with who said so and when, and a pass reads that file to decide that a slug is gone: it sends
no finding for a slug the file names, and tells no thread of that slug to carry on. `remove`
writes the file before the table, and `load` gives no row of a slug the file names, so a
removal that died between the two writes is still a removal. The row as it was becomes one
line of `transitions.jsonl`, and the stored brief moves to
`removed/<slug>.<the first 12 of its sha>.md`. `add` refuses a slug the file names. A
`removed.json` that does not parse is `Unparsable`, as the table is: nothing launches and no
verb writes until someone mends it.

`hold` sets `held` and `approve` clears it; a row that was never approved has none. `merge_after` is
the slugs of rows whose pull requests merge before this row's. `add` writes `merge_after` again,
along with `depends`, using the value of `--merge-after`, and refuses an order that jmerge could
never keep (`_merge_after`). `jmerge` reads `merge_after` and `held` (`jmerge.rows`). When `hold`
has taken back a row's go, jmerge does not merge the row's pull request until the user approves the
row again, just as no pass launches such a row. A row named in `merge_after` that is not `merged` or
`done` keeps the pull requests that name it from merging. `depends` gates a launch and says nothing
of a merge.

`entry` is the Chef's column that only `add` writes: the slug of the plan entry that the row does
work for, where that is not the row's own slug. An entry is often several briefs, and `jbus plan`
counts an entry's status by the rows that name it (`jbus.plan`). A row with no `entry` is its
own entry (`entry`).

`item` is the other column only `add` writes: the id of the work item that the row
represents (`jbus.item`). Once a row has one, jbus refuses an `add` that names another.

jbus runs the verbs as a batch, every one or none (`apply`). It applies each verb to the table
and the briefs in memory, and writes the files once the last one is done. A verb typed alone
is a batch of one.
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
from jbriefs import chains, meaning
from jbriefs import parse as briefs
from jbus import Refused, write_json

EVENTS = {"queue": "quiet"}
CHEF = ("slug", "priority", "depends", "merge_after", "approved", "brief_sha", "entry")
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
_SENT_TO = ("Home:", "Thread:", "Green main:")
PAGE = "page"
BASES = ("word", "answer", "message", PAGE)
BASIS = (
    "--word <id>, --answer <number>, --message <thread id>/<message id> or --page "
    "<session key>/<entry id>"
)
RULE = "rule"
BY_RULE = "--rule <n> with --follows <parent slug>"
FOLLOWED = "a follow-up approved by rule has no go without its parent's"
CLEANUP = "cleanup-"
FOLLOW_UP = (
    "a row is a follow-up of the row P, and jbus approves it by the home's follow-up rule when it "
    "is queued, when it names P (its brief's head has a line `Follows: P`, or its slug is "
    "`cleanup-P`), when it is P's (its slug is `cleanup-P`, or its --entry is P's plan entry), "
    "and when P's go is the user's own and holds (P is a row of the queue, or went as merged, "
    "and was approved by the user's word and not by a rule); any other row waits for the user's go"
)
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
    """Return where jbus keeps the stored brief of a removed row."""
    return state / "removed" / f"{slug}.{brief_sha(text)[:12]}.md"


def removed(state: Path) -> dict[str, dict[str, str]]:
    """Return the slugs removed for good, each with the `at` and `by` that its `remove` got."""
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
    """Return the removed slugs, for callers that only leave them out. Where the file does not
    parse, it returns none: `load` reports that, and a pass then sends a gate for the file."""
    try:
        return frozenset(removed(state))
    except Unparsable:
        return frozenset()


def clock() -> datetime:
    """Return the time at which an approval runs, which is also the time jbus writes on a
    removal's line of `transitions.jsonl`."""
    return datetime.now(UTC)


def runner() -> dict[str, str]:
    """Return who runs the command: the session that the environment names, and the directory."""
    return {"session": os.environ.get(SESSION, ""), "directory": str(Path.cwd())}


def who(ran_by: dict[str, str]) -> str:
    """Return who ran a command, as `runner` found it: the home of the directory in which it
    ran, or a shell where no session ran it."""
    directory = ran_by.get("directory", "")
    if not ran_by.get("session"):
        return f"a shell in {directory}"
    return f"the {Path(directory).name} home"


@dataclass(frozen=True)
class Said:
    """`Said` holds the user's words as their store recorded them: when and where the user said
    them, and whether jbus read the words and the time in T3 Code or Lavish (`checked`) or
    someone typed them. `ref` is the `<thread id>/<message id>` or `<session key>/<entry id>`
    in which jbus read them, or nothing."""

    words: str
    said_at: str
    said_in: str
    checked: bool
    ref: str = ""


@dataclass(frozen=True)
class Approval:
    """An `Approval` is the record of a row's go. `basis` is one of `BASES`, and `ref` names the
    record of that basis: a word's id, a question's number, `<thread id>/<message id>`, or, for
    `PAGE`, `<session key>/<entry id>`, whose `said_in` is the page's file. `ran_by` is `runner` and
    `ran_at` is the clock, both as jbus found them: no option gives either.

    With the basis `RULE`, `ref` is the rule's number, `words` is the rule's text and `follows` is
    the slug of the parent row. The user said nothing of the row, so `said_at` and `said_in` are
    empty. No other basis has a `follows`, and the record of such a basis has none.

    `brief_sha` is the stored brief's sha at the go, `meaning` is its fingerprint and `scope`
    is the sha256 of that fingerprint (`jbriefs.meaning`): the go holds for a brief that means
    the same. An older record, made before the fingerprint, has none of the three, and the
    row's `brief_sha` is the sha of the brief that the user approved."""

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
            return f"{parent}; run {self.ran_at} by {self.who()}; you did not speak of this row"
        ran = f"run {self.ran_at} by {self.who()}"
        if self.basis == PAGE:
            return f"your pick on a Lavish page, {self.said_at}, {Path(self.said_in).name}; {ran}"
        typed = "" if self.checked else " (time typed)"
        where = f", in {self.said_in}" if self.said_in else ""
        return f"your word, {self.said_at}{typed}{where}; {ran}"


def record(row: Row) -> Approval | None:
    """Return the row's approval as a record, or None for a row with none or with a typed
    string."""
    try:
        return Approval(**row["approval"]) if row.get("approval") else None
    except TypeError:
        return None


def approval(row: Row) -> str:
    """Return what jbus says of a row's go: the record's line, the typed string of an older row
    with what it is, or nothing for a row with no go."""
    kept, typed = record(row), row.get("approved", "")
    if kept:
        return kept.line()
    return f"{typed} (typed, not checked)" if typed else ""


def held(made: Approval) -> dict[str, Any]:
    """Return the record in the form that a row stores, with `follows` only where the approval
    has a parent."""
    return {name: value for name, value in asdict(made).items() if name != "follows" or value}


_NUMBERED = re.compile(r"\d+\. ")


def rule(standing: Path, number: str) -> Said:
    """Return rule `number` of a home's standing rules, as the file has it now: the line that
    starts `<number>. `, up to the next numbered line or heading. jbus reads the file and
    never writes it."""
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
    """Return when the row's approval ran, by its record. A typed string gives no time."""
    kept = record(row)
    return kept.ran_at if kept else ""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def body(text: str) -> str:
    """Return the brief with no `Home:`, `Thread:` or `Green main:` line in its head, the
    lines above its first `## `. The first two name the threads that receive the brief, and
    they are left out because a brief is the same brief under another home. A launch writes the
    third (`dispatch`). A launch sends this text, so every line that a launch sends is a line
    that `brief_sha` covers."""
    kept, head = [], True
    for line in text.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(_SENT_TO)):
            kept.append(line)
    return "".join(kept)


def brief_sha(text: str) -> str:
    """Return the sha256 of the brief's `body`. jbus uses it to approve, show and launch the
    brief."""
    return sha(body(text))


def fingerprint(text: str) -> meaning.Meaning:
    """Return what the brief asks for, with its `Home:` and `Thread:` lines left out
    (`jbriefs.meaning`)."""
    return meaning.meaning(body(text))


def approved_text(row: Row, text: str) -> bool:
    """Return whether the row's go holds for the brief `text`.

    A go recorded with a fingerprint, or bound to one by an `add` (`rebound`), holds for every
    brief that means the same (`meaning.same`), whatever its wording. An older go holds only for
    the text the user approved: its row's `brief_sha`. For a row approved before `brief_sha` left
    out the two lines, it is the sha256 of the whole text, line for line.
    """
    bound = _bound(row)
    if bound:
        return meaning.same(bound, fingerprint(text))
    return row.get("brief_sha") in (brief_sha(text), sha(text))


def _bound(row: Row) -> meaning.Meaning:
    """Return the fingerprint the row's go binds: its record's, or the one an `add` bound an older
    go to (`rebound`). Return nothing for a go bound only to a sha."""
    kept = record(row)
    return kept.meaning if kept and kept.scope else row.get("rebound", [])


def changed(row: Row, text: str | None) -> list[str]:
    """Return the lines of the brief `text` that the row's go does not cover, as
    `meaning.changed` names them. A go bound only to a sha, and a brief that is gone, have no
    lines to name, and each says so in one line."""
    if text is None:
        return ["the stored brief is gone"]
    bound = _bound(row)
    if not bound:
        return ["the go is bound to a sha of the whole brief, so no line can be named"]
    return meaning.changed(bound, body(text))


def verify(row: Row, text: str | None, path: str) -> dict[str, Any]:
    """Return what another reader needs to check a go: the row's record, and the brief at
    `path` with its sha, its fingerprint and whether the go holds for it."""
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
        "rebound": row.get("rebound", []),
        "brief": now,
    }


def brief(state: Path, slug: str) -> str | None:
    try:
        return brief_path(state, slug).read_text()
    except OSError:
        return None


def _well_formed(row: Any) -> bool:
    """Return whether a row's Chef columns have the types that every pass needs to sort and
    compare rows."""
    return (
        isinstance(row, dict)
        and isinstance(row.get("slug"), str)
        and type(row.get("priority", 0)) is int
        and isinstance(row.get("depends", []), list)
        and all(isinstance(slug, str) for slug in row.get("depends", []))
        and type(row.get("held", False)) is bool
        and isinstance(row.get("merge_after", []), list)
        and all(isinstance(slug, str) for slug in row.get("merge_after", []))
        and isinstance(row.get("entry", ""), str)
        and isinstance(row.get("approved", ""), str)
        and isinstance(row.get("approval", {}), dict)
        and isinstance(row.get("brief_sha", ""), str)
        and isinstance(row.get("item", ""), str)
    )


def fresh(state: Path, slug: str) -> Row | None:
    """Return the row as it is now, read under the same lock that the verbs hold when they write."""
    return current(state, slug)[0]


def current(state: Path, slug: str) -> tuple[Row | None, str | None]:
    """Return the row and its stored brief as they are now, both read under the lock that the
    verbs hold while they write the table and the briefs. A batch writes both under it, so the
    two are of one moment: a row is never judged against a brief that a later `add` wrote."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "queue.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            row = next((row for row in load(state) if row["slug"] == slug), None)
        except Unparsable:
            return None, None
        return row, brief(state, slug)


def load(state: Path) -> list[Row]:
    """Return the rows of the table, leaving out any row of a slug that `removed.json`
    names."""
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
    """Return whether a row is finished and leaves nothing: merged or done, with no reason to
    wait."""
    return row.get("status") in FINAL and not row.get("why")


def entry(row: Row) -> str:
    """Return the plan entry that the row does work for: the entry given to `add`, or the row's
    own slug."""
    return row.get("entry") or row["slug"]


def order(row: Row) -> tuple[int, str]:
    return (row.get("priority", 0), row["slug"])


def _was(slug: str, gone: dict[str, dict[str, str]]) -> str:
    return f"{slug} was removed {gone[slug].get('at', '')} by {gone[slug].get('by', '')}"


def was_removed(state: Path, slug: str) -> str:
    """Return the line that says who removed the slug and when, or nothing for a slug that
    was not removed."""
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
    """`Add` is the verb that adds a new row, or gives a row its brief, priority, depends and
    merge_after again. It leaves the row's approval as it is, and its entry too where `entry`
    is empty. An `entry` that is the row's own slug takes the row's entry away: the row is
    then its own entry, and holds none."""

    slug: str
    priority: int
    depends: list[str]
    text: str
    entry: str = ""
    item: str = ""
    merge_after: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Approve:
    """`Approve` is the verb that records the user's go for the brief whose sha256 starts with
    `given`, on the words that `ref` names. For a go by a rule, `ref` is the rule's number and
    `follows` is the parent row's slug."""

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
    """`Remove` is the verb that removes a row for good, on the user's word."""

    slug: str
    by: str
    at: str


Verb = Add | Approve | Hold | Remove


@dataclass(frozen=True)
class Asks:
    """`Asks` holds the calls that a `remove` and an `approve` make outside the table.

    `out` describes in one line the work of a slug that is out, or returns nothing. It may take
    seconds, so jbus calls it before it locks the table. `launched` says whether a launch of the
    slug is under way or happened since jbus called `out`, and jbus calls it with the table locked.
    `told` gets each removal's line of `transitions.jsonl`, once `removed.json` names the slug.
    `said` gets an approval's basis and reference, and returns the user's words that the basis and
    reference name or the text of the standing rule, or refuses. It may ask T3 Code, so jbus also
    calls it before it locks the table.

    `follow` is the number of the home's standing rule that a follow-up of approved work needs no
    new approval, or nothing where the home has none: then jbus approves no row by rule itself.
    """

    out: Callable[[str], str]
    launched: Callable[[str], str]
    told: Callable[[dict[str, Any]], None]
    said: Callable[[str, str], Said] | None = None
    follow: str = ""


_OPTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "add": (("priority",), ("depends", "merge-after", "entry")),
    "approve": (("sha",), (*BASES, RULE, "follows", "by", "at")),
    "hold": ((), ()),
    "remove": (("by", "at"), ()),
}
_BRIEF, _END = "--- brief ", "--- end"


def basis(given: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the one basis that an `approve` was given, its reference, and the parent that a
    rule's follow-up names. `basis` refuses no basis or more than one, a rule with no parent,
    a parent with no rule, and a name or a time beside the basis."""
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
    """`_Batch` holds what a batch has done so far, in memory: nothing reaches disk until its last
    verb is done."""

    state: Path
    rows: list[Row]
    gone: dict[str, dict[str, str]]
    briefs: dict[str, str | None]
    moves: list[dict[str, Any]]
    aside: dict[Path, str]
    queued: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)

    def brief(self, slug: str) -> str | None:
        return self.briefs[slug] if slug in self.briefs else brief(self.state, slug)

    def row(self, slug: str) -> Row:
        return _row(self.rows, slug, self.gone)


def _went(batch: _Batch, slug: str) -> Row | None:
    """Return the row of a removed slug as it was when it went: the copy in this batch, or
    else the copy in the last line of `transitions.jsonl` that removed it."""
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
    """Refuse a follow-up whose parent is not a row that the user approved with their own word.

    The parent is a row of the table, or one that was removed after it merged. The parent's
    approval is a record by one of `BASES`, or the typed string of an older row. `_parent` refuses a
    parent that a rule approved. It also refuses to approve by a rule a row that another row
    follows, since the rule approval would write over that row's own word. So nothing is
    more than one step away from the user's word.
    """
    cannot = f"refused: {slug} cannot follow"
    if follows == slug:
        raise Refused(f"{cannot} itself")
    behind = sorted(row["slug"] for row in batch.rows if (record(row) or Approval).follows == slug)
    if behind:
        raise Refused(
            f"{cannot} {follows}: {', '.join(behind)} follow {slug}, and a chain is one step: "
            f"take the user's word for {slug}"
        )
    row, here = _parent_row(batch, slug, follows)
    made = record(row)
    if made and made.basis == RULE:
        raise Refused(
            f"{cannot} {follows}: {follows} was approved by rule {made.ref} as a follow-up of "
            f"{made.follows}, and a chain is one step: follow {made.follows}, or take the user's "
            f"word for {slug}"
        )
    if not row.get("approved"):
        raise Refused(f"{cannot} {follows}: {follows} has no approval")
    text = batch.brief(follows) if here else None
    if text is not None and not approved_text(row, text):
        raise Refused(f"{cannot} {follows}: {follows}'s brief changed after its approval")


def _parent_row(batch: _Batch, slug: str, follows: str) -> tuple[Row, bool]:
    """Return the parent's row, and whether it is in the table. A removed parent is its row as it
    went, and only one that went as merged is a parent."""
    cannot = f"refused: {slug} cannot follow"
    row = next((row for row in batch.rows if row["slug"] == follows), None)
    if row is not None:
        return row, True
    if follows not in batch.gone:
        raise Refused(f"{cannot} {follows}: the queue has no row {follows}")
    went = _went(batch, follows)
    if went is None or went.get("status") != "merged":
        was = _was(follows, batch.gone)
        raise Refused(f"{cannot} {follows}: {was}, and its row did not go as merged")
    return went, False


def named_parent(slug: str, text: str) -> str:
    """Return the parent a row names: the first `Follows:` line of its brief's head, or else, for a
    row a review filed, the slug after `cleanup-`. Return nothing for a row that names none."""
    named = [lines[0].strip() for label, lines in briefs.fields(text) if label == "Follows"]
    if named:
        return named[0]
    return slug.removeprefix(CLEANUP) if slug.startswith(CLEANUP) else ""


def follow_up(batch: _Batch, slug: str) -> str:
    """Return the parent that the row `slug` follows up by the follow-up rule, or refuse with why
    the row is not a follow-up. The rule is `FOLLOW_UP`, and it reads the row, its brief and the
    parent's row, never a judgment. The parent's go must be the user's own (`_parent`), so a
    follow-up of a follow-up waits for the user."""
    named = named_parent(slug, batch.brief(slug) or "")
    if not named:
        raise Refused(f"refused: {slug} names no parent: no Follows: line, and no cleanup- slug")
    parent, _ = _parent_row(batch, slug, named)
    if slug != f"{CLEANUP}{named}" and entry(batch.row(slug)) != entry(parent):
        raise Refused(
            f"refused: {slug} does not do work for {named}'s plan entry {entry(parent)}: "
            f"its entry is {entry(batch.row(slug))}"
        )
    _parent(batch, slug, named)
    return named


def _by_rule(
    batch: _Batch,
    slug: str,
    user: jsettings.Settings | None,
    asks: Asks,
    said: dict[tuple[str, str], Said | Refused],
) -> str:
    """Approve by the follow-up rule a row that waits for a go and has no hold, and return the line
    that says so. Return the reason for a row that names a parent and is no follow-up, and nothing
    for one that names none: either waits for the user's go."""
    row = next((row for row in batch.rows if row["slug"] == slug), None)
    text = batch.brief(slug)
    if row is None or text is None or row.get("held") or row.get("status", "queued") != "queued":
        return ""
    if row.get("approved") and approved_text(row, text):
        return ""
    try:
        parent = follow_up(batch, slug)
        verb = Approve(slug, RULE, asks.follow, brief_sha(text)[:12], parent)
        return _do(verb, batch, user, asks, {}, said)
    except Refused as error:
        if not named_parent(slug, text):
            return ""
        why = str(error).removeprefix("refused: ")
        return f"{slug} waits for the user's go, not a follow-up by rule {asks.follow}: {why}"


def _followers(batch: _Batch) -> list[str]:
    """Return the rows that the follow-up rule is asked of at the end of a batch: each row the
    batch queued new, or queued again where its go was by rule, and each row with no go that names
    a parent the batch approved by the user's word. A row that already waited for the user is asked
    again only when its parent gets that word, so a re-add never turns a row the user left into a
    go."""
    waiting = [
        row["slug"]
        for row in batch.rows
        if not row.get("approved")
        and named_parent(row["slug"], batch.brief(row["slug"]) or "") in batch.parents
    ]
    return list(dict.fromkeys([*batch.queued, *waiting]))


def _hold(row: Row) -> None:
    row.update(approved="", brief_sha="", held=True)
    row.pop("approval", None)
    row.pop("rebound", None)


def _unfollow(rows: list[Row], parent: str) -> list[str]:
    """Take the go back from each row that is still queued and was approved as a follow-up of
    `parent`, since its go depended on the parent's go, which is gone. Return their slugs. A row
    that was launched keeps its record, since nothing takes a launch back."""
    held = []
    for row in rows:
        made = record(row)
        if made and made.follows == parent and row.get("status", "queued") == "queued":
            _hold(row)
            held.append(row["slug"])
    return sorted(held)


def _builds_on(rows: list[Row], verb: Add) -> None:
    """Refuse a depends that the brief does not build on. A depends holds the row's launch until
    the other row has merged, which costs the row that row's whole cycle, so it is only for a row
    whose brief's `Builds on:` line names the other (`jbriefs.chains.builds_on`). An order that is
    only about merging is `merge_after`, and the row launches at once. A depends the row already
    has is not checked again, so an add that only changes a row's priority or brief goes through
    for a row queued before this check."""
    had = next((row.get("depends", []) for row in rows if row["slug"] == verb.slug), [])
    named = chains.builds_on(body(verb.text))
    for other in verb.depends:
        if other not in had and other not in named:
            raise Refused(
                f"refused: {verb.slug} cannot depend on {other}: its brief's Builds on: line "
                f"does not name {other}. A depends is for a row that starts from {other}'s "
                f"work, and the brief's Builds on: line says what of it; an order that is only "
                f"about merging is --merge-after {other}, and the row launches at once"
            )


def _merge_after(batch: _Batch, verb: Add) -> None:
    """Refuse an order that jmerge could not keep. There are three such orders. In the first, a row
    merges after itself. In the second, a row merges after a slug that was removed or that has no
    row in the table. In the third, a row merges after a row that in turn merges after it or depends
    on it, which would leave both rows waiting for ever. This check does not refuse a loop of
    `depends` alone: the stall check names it. Rows of the batch count as they are when the verb
    runs."""
    edges = {
        row["slug"]: [
            *((slug, True) for slug in row.get("merge_after", [])),
            *((slug, False) for slug in row.get("depends", [])),
        ]
        for row in batch.rows
    }
    ahead_of = [
        *((slug, True) for slug in verb.merge_after),
        *((slug, False) for slug in verb.depends),
    ]
    edges[verb.slug] = ahead_of
    for other in verb.merge_after:
        if other == verb.slug:
            raise Refused(f"refused: {verb.slug} cannot merge after itself")
        if other in batch.gone:
            raise Refused(
                f"refused: {verb.slug} cannot merge after {other}: {_was(other, batch.gone)}"
            )
        if other not in edges:
            raise Refused(
                f"refused: {verb.slug} cannot merge after {other}: the queue has no row {other}"
            )
    for other, ordered in ahead_of:
        seen, ahead = set(), [(other, ordered)]
        while ahead:
            here, through = ahead.pop()
            if here == verb.slug and through:
                said = "merge after" if ordered else "depend on"
                raise Refused(
                    f"refused: {verb.slug} cannot {said} {other}: {other} is already behind "
                    f"{verb.slug} by merge_after or depends, and neither would ever go"
                )
            if (here, through) not in seen:
                seen.add((here, through))
                ahead += [(slug, through or ma) for slug, ma in edges.get(here, [])]


def _new_faults(row: Row | None, was: str | None, text: str) -> list[str]:
    """Return the faults for which `add` refuses `text` (`jbriefs.parse.faults`).

    A lint runs when a row is first queued. A row whose go holds for `text` is already
    approved, so it is grandfathered. If the row's stored brief `was` already had a fault that a
    newer lint found, that fault does not refuse the row. Only a fault the edit brought
    refuses it.
    """
    faults = briefs.faults(body(text))
    if row and row.get("approved") and was is not None and approved_text(row, text):
        old = briefs.faults(body(was))
        return [fault for fault in faults if fault not in old]
    return faults


def grandfathered(state: Path, rows: list[Row]) -> list[tuple[str, list[str]]]:
    """Return the open rows whose go holds and whose stored brief now fails a lint: each
    slug with its faults, in the order of the table. The user approved them before the lint
    was added, and they keep their go and their launch."""
    found = []
    for row in sorted(rows, key=order):
        text = brief(state, row["slug"])
        if over(row) or not row.get("approved") or text is None or not approved_text(row, text):
            continue
        faults = briefs.faults(body(text))
        if faults:
            found.append((row["slug"], faults))
    return found


def noted(state: Path, rows: list[Row]) -> str:
    """Return the lines at the end of `queue show`: the rows whose go no longer holds for the
    stored brief, and the grandfathered rows. Return nothing when there are none."""
    said = ""
    asked = reasked(state, rows)
    if asked:
        said += f"\nre-asked, the go does not hold for the stored brief: {', '.join(asked)}\n"
    kept = grandfathered(state, rows)
    if kept:
        said += (
            "\ngrandfathered, approved before a lint that refuses the brief now; the go stands:\n"
        )
        said += "".join(f"- {slug}: {'; '.join(faults)}\n" for slug, faults in kept)
    return said


def reasked(state: Path, rows: list[Row]) -> list[str]:
    """Return the slugs of the open rows that have a go which no longer holds for the stored
    brief. A pass gates such a row as `brief changed after approval` when it would launch it.
    The list also has the rows already launched, with a thread or a pull request, though no
    pass gates them again."""
    return [
        row["slug"]
        for row in sorted(rows, key=order)
        if not over(row)
        and row.get("approved")
        and not approved_text(row, brief(state, row["slug"]) or "")
    ]


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
        _merge_after(batch, verb)
        _builds_on(rows, verb)
        if verb.entry and not _SLUG.fullmatch(verb.entry):
            raise Refused(f"refused: --entry is a plan entry's slug, not {verb.entry}")
        if not verb.text.strip():
            raise Refused("refused: no brief on stdin")
        found = [row for row in rows if row["slug"] == verb.slug]
        faults = _new_faults(found[0] if found else None, batch.brief(verb.slug), verb.text)
        if faults:
            many = "1 fault" if len(faults) == 1 else f"{len(faults)} faults"
            lines = "".join(f"\n- {fault}" for fault in faults)
            raise Refused(f"refused: {verb.slug}'s brief has {many}, and nothing is queued{lines}")
        row = (
            found[0] if found else {"slug": verb.slug, "approved": "", "brief_sha": "", **_blank()}
        )
        if verb.item and row.get("item", verb.item) != verb.item:
            raise Refused(f"refused: {verb.slug} is linked to {row['item']}, not {verb.item}")
        row.update(priority=verb.priority, depends=verb.depends)
        row.pop("merge_after", None)
        if verb.merge_after:
            row["merge_after"] = verb.merge_after
        if verb.item:
            row["item"] = verb.item
        if verb.entry == verb.slug:
            row.pop("entry", None)
        elif verb.entry:
            row["entry"] = verb.entry
        was = batch.brief(verb.slug)
        kept = record(row)
        if was is not None and not _bound(row) and row.get("approved") and approved_text(row, was):
            row.update(brief_sha=brief_sha(was), rebound=fingerprint(was))
        if not found or (kept and kept.basis == RULE):
            batch.queued.append(verb.slug)
        if not found:
            rows.append(row)
        batch.briefs[verb.slug] = verb.text
        depends = f", depends {', '.join(verb.depends)}" if verb.depends else ""
        if verb.merge_after:
            depends += f", merges after {', '.join(verb.merge_after)}"
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
        else:
            batch.parents.append(verb.slug)
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
        row.pop("held", None)
        row.pop("rebound", None)
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
        if verb.slug in (*other.get("depends", []), *other.get("merge_after", []))
        and other.get("status") != "merged"
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
    """Run every verb or none. A verb numbered 0 was typed alone, and jbus refuses it in that
    verb's own words.

    `user` is the user jbus checks a `remove` against, and jbus writes an approval's time in
    that user's zone: `add` and `hold` read no settings. `asks` holds the calls that a `remove`
    and an `approve` make outside the table, and a batch with either verb needs it.

    A removal is done once `removed.json` names its slug, and after that `load` gives no row
    of that slug. The batch writes the brief's copy aside and the line of `transitions.jsonl` before
    that, so the line names a file that exists. A batch that dies before it writes
    `removed.json` writes both again when it runs again: the copy's name is the brief's sha, so
    writing it twice is the same as once. After that the batch takes the stored brief away,
    then writes the event and the table. A batch that dies there leaves a removal with a
    brief still stored or with no event, and neither brings the row back.
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
    rule = asks.follow if asks is not None and asks.said is not None else ""
    for _, verb in verbs:
        asked = [(verb.basis, verb.ref)] if isinstance(verb, Approve) else []
        if rule and isinstance(verb, Add | Approve):
            asked.append((RULE, rule))
        for named in asked:
            if asks is not None and asks.said is not None and named not in said_by:
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
        if rule and asks is not None:
            for slug in _followers(batch):
                line = _by_rule(batch, slug, user, asks, said_by)
                if line:
                    said.append(line)
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
    merge_after: list[str] | None = None,
    user: jsettings.Settings | None = None,
    asks: Asks | None = None,
) -> list[str]:
    """Add the row, or its brief again, linked to the work item `item` where one is given.
    Return the line that says what was added, and the line of its approval by the follow-up rule
    or of why it waits, where `asks` names the rule (`_followers`)."""
    verb = Add(slug, priority, depends, text, entry, item, merge_after or [])
    return _run(state, [(0, verb)], user, asks)


def approve(
    state: Path,
    slug: str,
    rests: tuple[str, str, str],
    given: str,
    user: jsettings.Settings,
    asks: Asks,
) -> list[str]:
    """Record the go. `rests` is the basis, its reference and the parent, as `basis` returns
    them. Return the line of the go, and a line for each waiting follow-up of the row that the
    go lets the follow-up rule approve."""
    kind, ref, follows = rests
    return _run(state, [(0, Approve(slug, kind, ref, given, follows))], user, asks)


def hold(state: Path, slug: str) -> str:
    """Take the row's go back, and return the line that says what was held."""
    return _run(state, [(0, Hold(slug))])[0]


def remove(state: Path, slug: str, by: str, at: str, user: jsettings.Settings, asks: Asks) -> str:
    """Take the row out for good, and return the line that says what was done."""
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
    """Return a batch as its verbs, each with the number of the line it is on.

    A line is one of these:

    - `add <slug> --priority N [--depends a,b] [--merge-after a,b] [--entry <plan entry>]`;
    - `approve <slug> --sha <12>` with one of `--word <id>`, `--answer <number>`,
      `--message <thread id>/<message id>` and `--page <session key>/<entry id>`, or with
      `--rule <n> --follows <parent slug>`;
    - `hold <slug>`;
    - `remove <slug> --by <user> --at "<YYYY-MM-DD HH:MM ZONE>"`.

    The lines under an `add` are its brief, between a line `--- brief <slug>` and a line
    `--- end`. jbus takes the lines between as they are, so a brief cannot hold either marker
    as a line of its own.
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
                after = slugs(given.get("merge-after", ""))
                verbs.append((number, Add(slug, priority, depends, brief_text, of, "", after)))
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
    """`Change` is a row in which one of the columns in `SEEN` changed. It holds the row as it is
    now, and each such column with what it held before and what it holds now."""

    row: Row
    columns: dict[str, tuple[str, str]]


def derive(
    state: Path, facts: Callable[[Row], Row], stamp: str, at: str
) -> tuple[list[Row], list[Change]]:
    """Rewrite every row's derived columns with `facts`, and return which rows changed.

    `updated` moves only with one of the columns in `SEEN`, so a quiet pass leaves the table
    as it was. `since` moves only with `why`, and is empty when there is no reason. Neither
    of the two counts as a change of the table.

    Each status that changed becomes one line of `transitions.jsonl`: the slug, from, to,
    and `at`. The pass appends the line before it writes the table, so a pass that dies
    between the two reports a change twice and loses none.
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
            if column in ("depends", "merge_after"):
                value = ", ".join(value)
            elif column == "approved":
                value = approval(row)
            elif column == "brief_sha":
                value = str(value)[:12]
            cells.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def changes(changed: list[Change]) -> str:
    """Return what a pass changed: a line for each row with its columns as `from -> to`, then
    the table of those rows and of no other."""
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
    """Return the table of the open rows, with a last line that counts the finished ones.

    With `every`, or with no finished row, it is the whole table and no line more.
    """
    still = rows if every else [row for row in rows if not over(row)]
    left = len(rows) - len(still)
    if not left:
        return render(still)
    counted = "1 finished row" if left == 1 else f"{left} finished rows"
    return f"{render(still)}\n{counted} not shown: jbus queue show --all\n"
