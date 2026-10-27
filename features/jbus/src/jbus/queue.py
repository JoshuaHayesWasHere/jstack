"""The queue table has one row per brief, in `queue.json` under the project's state directory.

A row has two kinds of column, and each kind has one writer. Only the verbs here write the Chef's
columns: `add`, `approve`, `hold` and `remove`. Only a pass writes the derived columns, using what
T3 Code and GitHub say (`derive`), and no verb takes a derived column as input. Two derived columns
are a pair: `why` is the reason a row waits, and `since` is when that reason first held. jbus also
keeps each change of a row's status as one line of `transitions.jsonl` beside the table, and only
ever appends to that file.

When a row is first queued, `add` refuses a brief that a launch would refuse
(`jbriefs.parse.faults`), so nobody asks the user for a go on a brief that cannot launch. It also
refuses a brief that would ask the user mid-task, claim a shared doc, or copy an incident's text
into a test (`conduct`). A
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

One more basis is not the user's word for the row: a follow-up of approved work needs no new
approval (`RULE`, the rule in words is `FOLLOW_RULE`). Its ground is the go of the parent row it
names (`follows`), and the words jbus keeps are the rule and the line of that go. jbus knows the
rule by what it says and not by its number in a home's `standing.md`, which a home renumbers, so a
`--rule <n>` beside `--follows` is taken and not read. The parent's go is the user's word or this
rule's, and it holds for the parent's brief (`_parent`), so a chain of follow-ups goes back to the
user's word one go at a time, and the follow-up's line says that the user said nothing of it. A
`hold` of the parent, or a `remove` of a parent that did not merge, also takes back the go of every
queued follow-up down the chain from it.

jbus gives that go itself, to a row that the follow-up rule names a follow-up (`follow_up`, the rule
as jbus applies it is `FOLLOW_UP`), at the end of a batch (`_followers`, `_by_rule`): a row the
batch queued new, or queued again where its go was by rule, and a waiting row whose parent the batch
approved. Each pass gives it too (`follow_ups`), before any launch, to a waiting row of a
follow-up's kind (`KINDS`): a `cleanup-P`, a fix row jbus filed (`filed`), and a sync of an
integration branch. A filer queues its row as jbus's pass (`PASS`, kept as the row's `queued_by`)
with no approval, and the batch or the pass approves it. So no home approves a follow-up, and
nothing of it reaches the user. A fix jbus filed from a red check that no row's merge turned red
names no parent: its ground is the red run its brief names (`red_run`), and its record has no
`follows`.
A row whose go an edit voided is approved again only where its edit kept the parent its go named,
and a row the user's word approved waits for the user again.

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

`withdraw` is jbus's own `remove`, on no one's word, of a row that never launched and whose work
is gone, such as a fix for a red main that a later commit turned green (`watch._withdraw`). It
takes the row out the same way, by `jbus`, and keeps its reason as `why` in both its line of
`transitions.jsonl` and `removed.json`, so `was_removed` says why. It refuses a row that launched.

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
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import chains, meaning
from jbriefs import home as homes
from jbriefs import parse as briefs
from jbus import Refused, verbs, write_json

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
UNLAUNCHED = ("queued", "gate")
LIVE = (*UNLAUNCHED, "launched", "running", "waiting", "pr")
WITHDRAWN_BY = "jbus"
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
_SENT_TO = ("Home:", "Thread:", "Green main:", "Stacked on:")
PAGE = "page"
BASES = ("word", "answer", "message", PAGE)
BASIS = (
    "--word <id>, --answer <number>, --message <thread id>/<message id> or --page "
    "<session key>/<entry id>"
)
RULE = "rule"
BY_RULE = "--follows <parent slug>"
FOLLOW_RULE = "a follow-up of approved work needs no new approval"
FOLLOW_REF = "follow-up"
FOLLOWED = "a follow-up approved by rule has no go without its parent's"
CLEANUP = "cleanup-"
FILED = "none, jbus filed this from a red "
FROM_RED = "jbus filed it from the red run "
SYNC = "sync-main"
FOLLOW_UP = (
    "a row is a follow-up of the row P, and jbus approves it by the follow-up rule "
    f"({FOLLOW_RULE}) when it is queued and on each pass, when it names P (its brief's head has a "
    "line `Follows: P`, or its slug is `cleanup-P`), when it is of a follow-up's kind (its slug "
    "is `cleanup-P`; or it is a fix jbus filed, a row jbus's pass queued whose brief's Decisions: "
    f"line begins `{FILED}`; or it is a sync of an integration branch, its slug says `sync-main` "
    "and its pull request goes against a branch the home's integration file names; or, when it is "
    "queued, its --entry is P's plan entry), and when P's go holds (P is a row of the queue, or "
    "went as merged, and its go is the user's word or this rule's); a fix jbus filed that names "
    "no parent is approved by the same rule on the red run its brief's Task: line quotes; any "
    "other row waits for the user's go"
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
    """Return the slugs removed for good, each with the `at` and `by` that its `remove` got, and
    the `why` of a `withdraw`."""
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


def _home_name(home: Path, directory: Path) -> str:
    return "root" if directory == home else directory.name


def owned(
    home: Path, project: str, slug: str, text: str, adder: str | None, given: str | None
) -> None:
    """Refuse a row that a home adds for a brief whose home is another (`jbriefs.home.home_of`),
    so that two homes do not brief the same fix unseen. `adder` is the thread of the home that
    adds it (`--from`), the root home's when it is empty, and None when no home said it adds it.
    `given` is the home the row is handed over to on purpose (`--for`): `root` or a scope's name,
    which must be the brief's home."""
    theirs = _home_name(home, homes.home_of(home, text))
    if given is not None:
        if given != theirs:
            raise Refused(
                f"refused: --for {given}, and {slug}'s brief is the {theirs} home's: "
                "nothing is queued"
            )
        return
    if adder is None:
        return
    mine = home if not adder else None
    for where in (home, *(scope for scope, _, _ in homes.scopes(home))):
        if adder and homes.thread_of(where) == adder:
            mine = where
    if mine is None:
        raise Refused(
            f"refused: --from {adder} is no home of {project} now, its id is in no home-id: "
            "nothing is queued"
        )
    if _home_name(home, mine) != theirs:
        raise Refused(
            f"refused: {slug}'s brief is the {theirs} home's, and the {_home_name(home, mine)} "
            f"home adds it: the {theirs} home queues it, or this home hands it over with --for "
            f"{theirs}, and nothing is queued"
        )


def clock() -> datetime:
    """Return the time at which an approval runs, which is also the time jbus writes on a
    removal's line of `transitions.jsonl`."""
    return datetime.now(UTC)


PASS = {"session": "", "directory": "", "by": "jbus"}


def runner() -> dict[str, str]:
    """Return who runs the command: the session that the environment names, and the directory."""
    return {"session": os.environ.get(SESSION, ""), "directory": str(Path.cwd())}


def who(ran_by: dict[str, str]) -> str:
    """Return who ran a command, as `runner` found it: the home of the directory in which it
    ran, or a shell where no session ran it. A pass of jbus's (`PASS`) is jbus's pass."""
    if ran_by.get("by") == PASS["by"]:
        return "jbus's pass"
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

    With the basis `RULE`, `ref` is `FOLLOW_REF`, `words` is the follow-up rule (`FOLLOW_RULE`)
    and the line of the parent's go, which is its ground, and `follows` is the slug of the parent
    row. A record from before the rule was known by what it says has the number the rule had in the
    home's `standing.md` as its `ref`, and that rule's text as its `words`. The user said nothing
    of the row, so `said_at` and `said_in` are empty. No other basis has a `follows`, and the
    record of such a basis has none.

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
            ruled = "the follow-up rule" if self.ref == FOLLOW_REF else f"rule {self.ref}"
            of = f"follow-up of {self.follows}" if self.follows else self.words.partition("; ")[2]
            parent = f"{ruled}, {of}"
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


def ran_at(row: Row) -> str:
    """Return when the row's approval ran, by its record. A typed string gives no time."""
    kept = record(row)
    return kept.ran_at if kept else ""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def body(text: str) -> str:
    """Return the brief with no `Home:`, `Thread:`, `Green main:` or `Stacked on:` line in its
    head, the lines above its first `## `. The first two name the threads that receive the brief,
    and they are left out because a brief is the same brief under another home. A launch writes
    the other two (`dispatch`). A launch sends this text, so every line that a launch sends is a
    line that `brief_sha` covers."""
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
    why = gone[slug].get("why", "")
    said = f"{slug} was removed {gone[slug].get('at', '')} by {gone[slug].get('by', '')}"
    return f"{said}: {why}" if why else said


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


@dataclass(frozen=True)
class Withdraw:
    """`Withdraw` is the removal of a row that never launched, for `why`: the work it asks for is
    no longer there to do (`withdraw`). `at` is when, in the user's zone, and `by` is who took it
    out: jbus's pass, or the home that ran `jbus queue withdraw`."""

    slug: str
    why: str
    at: str
    by: str = WITHDRAWN_BY


@dataclass(frozen=True)
class Rename:
    """`Rename` moves a row that never launched from `slug` to `new`, with its go (`rename`)."""

    slug: str
    new: str
    at: str
    by: str


Verb = Add | Approve | Hold | Remove | Withdraw | Rename


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

    `integration` is the branches that the home's `integration` file names: a sync of one of
    them is a follow-up's kind (`KINDS`).
    """

    out: Callable[[str], str]
    launched: Callable[[str], str]
    told: Callable[[dict[str, Any]], None]
    said: Callable[[str, str], Said] | None = None
    integration: tuple[str, ...] = ()


_OPTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "add": (("priority",), ("depends", "merge-after", "entry")),
    "approve": (("sha",), (*BASES, RULE, "follows", "by", "at")),
    "hold": ((), ()),
    "remove": (("by", "at"), ()),
}
_BRIEF, _END = "--- brief ", "--- end"


def basis(given: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the one basis that an `approve` was given, its reference, and the parent that a
    follow-up names. A `--follows` is the follow-up rule's basis, `RULE` with `FOLLOW_REF`, and a
    `--rule <n>` beside it is taken and not read: the rule is known by what it says. `basis`
    refuses no basis or more than one, a `--rule` with no parent, and a name or a time beside the
    basis."""
    named = [(name, str(given[name])) for name in BASES if given.get(name) not in (None, "")]
    follows = str(given.get("follows") or "")
    ruled = given.get(RULE) not in (None, "")
    if follows and not named:
        named = [(RULE, FOLLOW_REF)]
    stamped = any(given.get(name) is not None for name in ("by", "at"))
    if len(named) != 1 or (follows and named[0][0] != RULE) or (ruled and not follows) or stamped:
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


def _parent(batch: _Batch, slug: str, follows: str) -> Row:
    """Return the parent's row, or refuse a follow-up whose parent has no go that holds.

    The parent is a row of the table, or one that was removed after it merged. Its go is the user's
    word, a typed string of an older row, or the follow-up rule's, and it holds for the parent's
    stored brief. A parent approved by the rule is itself a follow-up, so a chain goes back to the
    user's word one go at a time, and since a parent must have its go first, no chain is a loop.
    """
    cannot = f"refused: {slug} cannot follow"
    if follows == slug:
        raise Refused(f"{cannot} itself")
    row, here = _parent_row(batch, slug, follows)
    if not row.get("approved"):
        raise Refused(f"{cannot} {follows}: {follows} has no approval")
    text = batch.brief(follows) if here else None
    if text is not None and not approved_text(row, text):
        raise Refused(f"{cannot} {follows}: {follows}'s brief changed after its approval")
    return row


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


def _ruled(row: Row) -> bool:
    """Return whether the row's go is the follow-up rule's."""
    made = record(row)
    return made is not None and made.basis == RULE


def _against(text: str) -> str:
    """Return the branch that the brief's `Pull request:` line opens its pull request against, or
    nothing where it names none."""
    for label, lines in briefs.fields(text):
        if label == "Pull request":
            found = re.search(r"\bagainst (\S+)", " ".join(lines))
            return found.group(1).rstrip(".,;") if found else ""
    return ""


def filed(row: Row, text: str) -> bool:
    """Return whether jbus filed the row from a red check: jbus's pass queued its brief (`PASS`),
    and the brief's `Decisions:` line says so (`FILED`). Who queued it is the record `add` keeps,
    so a filer needs no slug of its own here, and the same brief queued by a home is not one."""
    decided = [" ".join(lines) for label, lines in briefs.fields(text) if label == "Decisions"]
    by = row.get("queued_by") or {}
    return by.get("by") == PASS["by"] and bool(decided) and decided[0].startswith(FILED)


def red_run(text: str) -> str:
    """Return the red run that a fix jbus filed names: the quoted words of its `Task:` line."""
    task = " ".join(next((lines for label, lines in briefs.fields(text) if label == "Task"), []))
    found = re.match(r'\s*"([^"]+)"', task)
    return found.group(1) if found else task.strip()


def kind(row: Row, text: str, branches: tuple[str, ...]) -> str:
    """Return the follow-up's kind that the row is (`KINDS`), or nothing: a `cleanup-P` is
    `cleanup`, a fix row jbus filed is `fix` (`filed`), and a row whose slug says `sync-main` and
    whose pull request goes against a branch that `branches` names is `sync`. The row and its brief
    say."""
    slug = row["slug"]
    if slug.startswith(CLEANUP):
        return "cleanup"
    if filed(row, text):
        return "fix"
    if SYNC in slug and _against(text) in branches:
        return "sync"
    return ""


KINDS = ("cleanup", "fix", "sync")


def follow_up(batch: _Batch, slug: str, branches: tuple[str, ...] = (), units: bool = True) -> str:
    """Return the parent that the row `slug` follows up by the follow-up rule, nothing for a fix
    jbus filed from a red check that names no parent (`filed`), or refuse with why the row is not
    a follow-up. The rule is `FOLLOW_UP`, and it reads the row, its brief and the
    parent's row, never a judgment. A row of a follow-up's kind (`kind`) is one, and so, where
    `units` is set, is a row that does work for its parent's plan entry. The parent's go must
    hold (`_parent`). A row whose go an edit voided is one only where it names the parent its go
    named, and a row the user's word approved is never one: the user approves it again."""
    text = batch.brief(slug) or ""
    named = named_parent(slug, text)
    row = batch.row(slug)
    made = record(row)
    if row.get("approved") and (made is None or made.basis != RULE):
        raise Refused(f"refused: {slug} had the user's go, which its brief no longer holds")
    if not named and filed(row, text):
        if made and made.basis == RULE and made.follows:
            raise Refused(f"refused: {slug}'s go followed {made.follows}, and its brief names none")
        return ""
    if not named:
        raise Refused(f"refused: {slug} names no parent: no Follows: line, and no cleanup- slug")
    parent, _ = _parent_row(batch, slug, named)
    if made and made.basis == RULE and made.follows != named:
        raise Refused(
            f"refused: {slug}'s go followed {made.follows}, and its brief now follows {named}"
        )
    unit = units and entry(row) == entry(parent)
    if not kind(row, text, branches) and not unit:
        raise Refused(
            f"refused: {slug} is no follow-up's kind (cleanup-, a fix jbus filed, an integration "
            f"branch's sync) and does not do work for {named}'s plan entry {entry(parent)}: its "
            f"entry is {entry(row)}"
        )
    _parent(batch, slug, named)
    return named


def _by_rule(
    batch: _Batch,
    slug: str,
    user: jsettings.Settings | None,
    branches: tuple[str, ...],
    units: bool = True,
    ran_by: dict[str, str] | None = None,
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
        parent = follow_up(batch, slug, branches, units)
        verb = Approve(slug, RULE, FOLLOW_REF, brief_sha(text)[:12], parent)
        return _do(verb, batch, user, None, {}, {}, ran_by)
    except Refused as error:
        if not named_parent(slug, text):
            return ""
        why = str(error).removeprefix("refused: ")
        return f"{slug} waits for the user's go, not a follow-up: {why}"


def _followers(batch: _Batch) -> list[str]:
    """Return the rows that the follow-up rule is asked of at the end of a batch: each row the
    batch queued new, or queued again where its go was by rule, and each row with no go that names
    a parent the batch approved. A row that already waited for the user is asked again only when
    its parent gets its go, so a re-add never turns a row the user left into a go."""
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
    `parent`, or of a row so held, down the chain, since its go depended on the parent's go,
    which is gone. Return their slugs. A row that was launched keeps its record, since nothing
    takes a launch back."""
    held, gone = [], [parent]
    while gone:
        one = gone.pop()
        for row in rows:
            made = record(row)
            if made and made.follows == one and row.get("status", "queued") == "queued":
                _hold(row)
                held.append(row["slug"])
                gone.append(row["slug"])
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


_QUOTED = re.compile(r'`[^`\n]*`|"[^"\n]*"|“[^”\n]*”')
_ASKS = re.compile(
    r"\bstops?(?: here)? and asks?\b|\bpauses? (?:and|to) ask\b"
    r"|(?<!home )\bask(?:s|ing)? the user\b|\b(?:check|confirm)s? with the user\b"
    r"|\bin the (?:crewmate|crew|scout)'s (?:own )?thread\b",
    re.IGNORECASE,
)
_GATED = "jbus gate"
_SHARED = re.compile(
    r"(?<![\w/.-])(?:readme\b|(?-i:(?!SKILL\.)[A-Z][A-Z_]*)\.md\b)|`docs/", re.IGNORECASE
)
_SWEEP = re.compile(r"\b(?:docs?|readme|documentation)\b", re.IGNORECASE)
_TESTED = re.compile(r"\b(?:tests?|fixtures?|cases?|examples?|samples?|evals?)\b", re.IGNORECASE)
_WORD = re.compile(r"[\w'-]+")
_RUN = 8


def _head(text: str) -> list[tuple[str, list[str]]]:
    """The fields of a brief's head, the lines above its first `## `, less its title."""
    return [
        (label, lines)
        for label, lines in briefs.fields(text)
        if label not in (briefs.TITLE, briefs.REST)
    ]


def asks(text: str, what: str = "brief") -> list[str]:
    """Why a brief or a scout's request would have its thread ask the user mid-task, as one fault.

    A line asks when it says `stops here and asks`, `ask the user`, `confirm with the user`, `in
    the crewmate's thread` or their kin (`_ASKS`), and `the home asks the user` is the home's to
    do. A quoted span, in backticks or double quotes, is somebody's words or a literal and is not
    read, and a line that names `jbus gate` routes its question the right way. The title is the
    task's name and is not read either.
    """
    for _, lines in _head(text):
        for line in lines:
            said = _ASKS.search(_QUOTED.sub("", line))
            if said and _GATED not in line:
                return [
                    f'{what} asks the user mid-task ("{said[0]}"): a crewmate or scout asks the '
                    "user nothing in its own thread: put the question to the user as a gate "
                    "through `jbus gate`"
                ]
    return []


def _runs(text: str) -> set[tuple[str, ...]]:
    """Every run of `_RUN` words in a row in `text`, lower-cased."""
    words = [word.lower() for word in _WORD.findall(text)]
    return {tuple(words[at : at + _RUN]) for at in range(len(words) - _RUN + 1)}


def conduct(text: str) -> list[str]:
    """The faults of a brief that its fields' own checks (`jbriefs.parse.faults`) do not see.

    - It asks the user mid-task (`asks`): a question is a gate through `jbus gate`.
    - Its `Done when:` or `Where:` claims a shared doc: the README or a Markdown file named in
      capitals at the repo's root (`CONTRIBUTING.md`, `AGENTS.md`, not a `SKILL.md`), or a page
      under a top-level `docs/` in backticks. A path with a folder before it, such as
      `features/<name>/README.md` or `features/<name>/docs/`, is a feature's own and not shared.
      Docs go to a docs sweep: a row whose title names docs, a README or documentation, and
      that row may claim them.
    - An item of its `Done when:` or `Proves it:` that names a test, a fixture or a case repeats
      `_RUN` words in a row (a hyphenated name is one word) of a quote on the `Task:` line,
      which says what happened: a test's text is small and made up, never an incident's text
      word for word. A quote is a span in double quotes or backticks. The other fields, such as
      `Decisions:`, may quote the user.
    """
    head = _head(text)
    found = asks(text)
    title = next((lines[0] for label, lines in briefs.fields(text) if label == briefs.TITLE), "")
    if not _SWEEP.search(title):
        for label, lines in head:
            said = _SHARED.search(" ".join(lines)) if label in ("Done when", "Where") else None
            if said:
                found.append(
                    f"brief's {label}: line claims a shared doc ({said[0]}): docs go to a "
                    "docs sweep, a row whose title names docs"
                )
    told = _runs(
        " ".join(
            quote.group(0)
            for label, lines in head
            if label == "Task"
            for quote in _QUOTED.finditer(" ".join(lines))
        )
    )
    for label, line in ((label, line) for label, lines in head for line in lines):
        tested = label in ("Done when", "Proves it") and _TESTED.search(line)
        copied = told & _runs(line) if tested else set()
        if copied:
            found.append(
                f"brief's {label}: line copies the Task line's quote word for word "
                f'("{" ".join(min(copied))}"): a test\'s text is small and made up, never an '
                "incident's text word for word"
            )
    return found


def faults(text: str) -> list[str]:
    """Every fault for which `add` refuses a brief: its fields' (`jbriefs.parse.faults`), then
    its conduct's (`conduct`)."""
    return [*briefs.faults(text), *conduct(text)]


def _new_faults(row: Row | None, was: str | None, text: str) -> list[str]:
    """Return the faults for which `add` refuses `text` (`faults`).

    A lint runs when a row is first queued. A row whose go holds for `text` is already
    approved, so it is grandfathered. If the row's stored brief `was` already had a fault that a
    newer lint found, that fault does not refuse the row. Only a fault the edit brought
    refuses it.
    """
    found = faults(body(text))
    if row and row.get("approved") and was is not None and approved_text(row, text):
        old = faults(body(was))
        return [fault for fault in found if fault not in old]
    return found


def grandfathered(state: Path, rows: list[Row]) -> list[tuple[str, list[str]]]:
    """Return the open rows whose go holds and whose stored brief now fails a lint: each
    slug with its faults, in the order of the table. The user approved them before the lint
    was added, and they keep their go and their launch."""
    found = []
    for row in sorted(rows, key=order):
        text = brief(state, row["slug"])
        if over(row) or not row.get("approved") or text is None or not approved_text(row, text):
            continue
        said = faults(body(text))
        if said:
            found.append((row["slug"], said))
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
    ran_by: dict[str, str] | None = None,
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
        _twin(batch, verb)
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
        row.update(priority=verb.priority, depends=verb.depends, queued_by=ran_by or runner())
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
        ruled = verb.basis == RULE
        if user is None or (not ruled and (verb.basis, verb.ref) not in said):
            raise Refused("refused: approve was given nothing to read the user's word with")
        row = batch.row(verb.slug)
        text = batch.brief(verb.slug)
        if text is None:
            raise Refused(f"refused: {verb.slug} has no brief, add it again")
        stored = brief_sha(text)
        if stored[:12] != verb.given:
            raise Refused(f"refused: {verb.slug}'s brief is {stored[:12]}, not {verb.given}")
        if ruled and row.get("approved") and approved_text(row, text) and not _ruled(row):
            raise Refused(
                f"refused: {verb.slug} has the user's go, which holds, and a follow-up's go "
                "would write over it"
            )
        if ruled and verb.follows:
            ground = approval(_parent(batch, verb.slug, verb.follows))
            rests = Said(f"{FOLLOW_RULE}; {verb.follows}'s go: {ground}", "", "", True)
        elif ruled:
            if not filed(row, text):
                raise Refused(f"refused: {verb.slug} names no parent, and jbus did not file it")
            rests = Said(f'{FOLLOW_RULE}; {FROM_RED}"{red_run(text)}"', "", "", True)
        else:
            rests = said[verb.basis, verb.ref]
        if isinstance(rests, Refused):
            raise rests
        batch.parents.append(verb.slug)
        means = fingerprint(text)
        made = Approval(
            basis=verb.basis,
            ref=FOLLOW_REF if ruled else verb.ref,
            words=rests.words,
            said_at=rests.said_at,
            said_in=rests.said_in,
            checked=rests.checked,
            ran_by=ran_by or runner(),
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
    if isinstance(verb, Withdraw):
        row = batch.row(verb.slug)
        _launching(row, asks)
        _waited_on(rows, verb.slug)
        return _take_out(batch, row, verb.slug, verb.by, verb.at, verb.why)
    if isinstance(verb, Rename):
        return _rename(batch, verb, asks)
    if user is None:
        raise Refused("refused: remove was given no settings to check --by and --at with")
    row = batch.row(verb.slug)
    theirs = verb.by != user.user
    if theirs and not _unlaunched(row):
        raise Refused(
            f"refused: {verb.slug} launched, and only {user.user} removes a row that launched, "
            f"not {verb.by}"
        )
    if not user.takes(verb.at):
        raise Refused(f'refused: --at is "{user.form(verb.at)}"')
    _waited_on(rows, verb.slug)
    if asks is None:
        raise Refused("refused: remove was given nothing to ask what is out with")
    is_out = out[verb.slug]
    if isinstance(is_out, Refused):
        raise is_out
    is_out = is_out or asks.launched(verb.slug)
    if is_out:
        raise Refused(f"refused: {is_out}")
    if theirs:
        why = f"withdrawn, not removed: only {user.user} removes a row, and {verb.slug}"
        why += " never launched"
        return _take_out(batch, row, verb.slug, who(ran_by or runner()), verb.at, why)
    return _take_out(batch, row, verb.slug, verb.by, verb.at)


def _unlaunched(row: Row) -> bool:
    """Return whether the row never launched: it has no thread, and it is queued, held or at a
    gate."""
    return not row.get("thread") and row.get("status", "queued") in UNLAUNCHED


def _launching(row: Row, asks: Asks | None) -> None:
    """Refuse a row that launched, or whose launch the launch records say is under way."""
    out = asks.launched(row["slug"]) if asks is not None else ""
    if out or not _unlaunched(row):
        raise Refused(f"refused: {row['slug']} launched, and its crew has it")


def _unheaded(text: str, slug: str) -> str:
    """Return the brief's `body` with its `# <slug>:` head line taken out: what the brief asks
    for under any slug."""
    first, _, rest = body(text).partition("\n")
    return (rest if first.startswith(f"# {slug}:") else f"{first}\n{rest}").strip()


def _twin(batch: _Batch, verb: Add) -> None:
    """Refuse a brief that another row still at work has under another slug: two rows for one
    brief would launch the work twice."""
    mine = _unheaded(verb.text, verb.slug)
    for row in batch.rows:
        other = row["slug"]
        if other == verb.slug or row.get("status", "queued") not in LIVE:
            continue
        text = batch.brief(other)
        if text is not None and _unheaded(text, other) == mine:
            status = "held" if row.get("held") else row.get("status", "queued")
            raise Refused(
                f"refused: {verb.slug}'s brief is {other}'s ({status}): rename by "
                f"`jbus queue rename {other} {verb.slug}`, or withdraw one"
            )


def _rename(batch: _Batch, verb: Rename, asks: Asks | None) -> str:
    """Move an unlaunched row to the slug `new`, with its columns and its go. The brief's head
    line is rewritten, and the rest of it is the brief the go was given for, so a go that held
    is bound to the renamed brief. A row that was its own plan entry keeps the old slug as its
    entry. The old slug goes into `removed.json`, so the pass drops its item and no add brings it
    back; the row gets its item anew from the pass."""
    rows, old, new = batch.rows, verb.slug, verb.new
    row = batch.row(old)
    _launching(row, asks)
    if not _SLUG.fullmatch(new):
        raise Refused(f"refused: {new} is not a slug")
    if new in batch.gone:
        raise Refused(f"refused: {_was(new, batch.gone)}, and a removed slug is not added again")
    if any(other["slug"] == new for other in rows):
        raise Refused(f"refused: the queue has a row {new}")
    naming = sorted(
        other["slug"]
        for other in rows
        if other is not row
        and (
            old in (*other.get("depends", []), *other.get("merge_after", []))
            or other.get("entry") == old
            or getattr(record(other), "follows", "") == old
        )
    )
    if naming:
        raise Refused(f"refused: {', '.join(naming)} names {old}, so {old} keeps its slug")
    text = batch.brief(old)
    if text is None:
        raise Refused(f"refused: {old} has no brief, add it again")
    first, cut, rest = text.partition("\n")
    head = f"# {old}:"
    renamed = f"# {new}:{first.removeprefix(head)}{cut}{rest}" if first.startswith(head) else text
    holds = bool(row.get("approved")) and approved_text(row, text)
    if holds:
        kept = record(row)
        if kept and kept.scope:
            means = fingerprint(renamed)
            bound = replace(
                kept,
                brief_sha=brief_sha(renamed),
                scope=meaning.fingerprint(means),
                meaning=means,
            )
            row["approval"] = held(bound)
        elif row.get("rebound"):
            row["rebound"] = fingerprint(renamed)
        row["brief_sha"] = brief_sha(renamed)
    row["slug"] = new
    row.setdefault("entry", old)
    row.pop("item", None)
    batch.gone[old] = {"at": verb.at, "by": verb.by, "why": f"renamed to {new}"}
    batch.briefs[old] = None
    batch.briefs[new] = renamed
    go = GO_HOLDS if holds else ""
    return f"renamed {old} to {new}: brief {brief_sha(renamed)[:12]}{go}"


def _waited_on(rows: list[Row], slug: str) -> None:
    """Refuse to take out a row that another row depends on or merges after."""
    waits = sorted(
        other["slug"]
        for other in rows
        if slug in (*other.get("depends", []), *other.get("merge_after", []))
        and other.get("status") != "merged"
    )
    if waits:
        raise Refused(f"refused: {', '.join(waits)} wait on {slug}: remove them first")


def _take_out(batch: _Batch, row: Row, slug: str, by: str, at: str, why: str = "") -> str:
    """Take the row out of the batch for good: its line of `transitions.jsonl`, its slug in
    `removed.json` and its brief kept aside. `why` is a withdraw's reason, kept in both."""
    rows, text = batch.rows, batch.brief(slug)
    kept = None
    if text is not None:
        kept = aside_path(batch.state, slug, text)
        batch.aside[kept] = text
    was = row.get("status", "queued")
    move = {
        "slug": slug,
        "from": was,
        "to": "removed",
        "at": clock().astimezone(UTC).isoformat(timespec="seconds"),
        "by": by,
        "said": at,
        "row": dict(row),
        "brief": str(kept) if kept else "",
    }
    batch.moves.append(move | ({"why": why} if why else {}))
    rows.remove(row)
    batch.gone[slug] = {"at": at, "by": by} | ({"why": why} if why else {})
    batch.briefs[slug] = None
    where = f"brief kept at {kept}" if kept else "it had no stored brief"
    also = [] if was == "merged" else _unfollow(rows, slug)
    more = f", and held {', '.join(also)}: {FOLLOWED}" if also else ""
    said = f"removed {slug}: was {was}, {at} by {by}, {where}{more}"
    return f"{said}: {why}" if why else said


def _none(line: int, error: Exception) -> Refused:
    said, *more = str(error).removeprefix("refused: ").split("\n")
    lines = "".join(f"\n{one}" for one in more)
    return Refused(f"refused: line {line}: {said}, and nothing in the batch was applied{lines}")


def _run(
    state: Path,
    verbs: list[tuple[int, Verb]],
    user: jsettings.Settings | None = None,
    asks: Asks | None = None,
    ran_by: dict[str, str] | None = None,
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

    A rename writes the new brief and the table before `removed.json` retires the old slug, since
    `load` drops a row whose slug is there: a batch that dies before that leaves the row under its
    new slug, with its go, and the old slug not retired.
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
        asked = [(verb.basis, verb.ref)] if isinstance(verb, Approve) and verb.basis != RULE else []
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
        batch = _Batch(state, rows, dict(gone), {}, moves, {})
        for line, verb in verbs:
            try:
                said.append(_do(verb, batch, user, asks, out, said_by, ran_by))
            except Refused as error:
                if not line:
                    raise
                raise _none(line, error) from error
        if user is not None and (asks is not None or ran_by is not None):
            for slug in _followers(batch):
                line = _by_rule(batch, slug, user, asks.integration if asks else (), ran_by=ran_by)
                if line:
                    said.append(line)
        for kept, text in batch.aside.items():
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_text(text)
        if batch.moves:
            with open(transitions_path(state), "a") as log:
                log.writelines(json.dumps(move) + "\n" for move in batch.moves)
        if any(isinstance(verb, Rename) for _, verb in verbs):
            for slug, text in batch.briefs.items():
                if text is not None:
                    brief_path(state, slug).write_text(text)
            rows.sort(key=order)
            write_json(path(state), rows)
        if batch.gone != gone:
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
    ran_by: dict[str, str] | None = None,
) -> list[str]:
    """Add the row, or its brief again, linked to the work item `item` where one is given.
    Return the line that says what was added, and the line of its approval by the follow-up rule
    or of why it waits, where `asks`, or a `user` with `ran_by`, names the rule (`_followers`).
    `ran_by` is who queued it, `runner` where none is given: a filer gives `PASS`, and the row
    keeps it as `queued_by`, which makes its fix a fix jbus filed (`filed`)."""
    verb = Add(slug, priority, depends, text, entry, item, merge_after or [])
    return _run(state, [(0, verb)], user, asks, ran_by)


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


def follow_ups(state: Path, branches: tuple[str, ...], user: jsettings.Settings) -> list[str]:
    """Approve by the follow-up rule each waiting row of a follow-up's kind (`KINDS`) whose
    parent's go holds, as jbus's pass (`PASS`), and return the line of each go. A row approved here
    may be the parent of another, so the rows are asked again until a round approves none. A row
    that is no follow-up is left to the user, and nothing is said of it: each pass asks it
    again."""
    said: list[str] = []
    with _changing(state) as rows:
        try:
            gone = removed(state)
        except Unparsable:
            return said
        batch = _Batch(state, rows, gone, {}, [], {})
        while True:
            lines = [
                line
                for row in sorted(rows, key=order)
                if kind(row, batch.brief(row["slug"]) or "", branches)
                for line in [_by_rule(batch, row["slug"], user, branches, False, PASS)]
                if line.startswith("approved ")
            ]
            said += lines
            if not lines:
                return said


def _follow_ups(half: Any) -> None:
    """Run `follow_ups` as a step of the pass, before the queue is read for any launch, so a
    follow-up a filer queued last pass launches on this one."""
    run = half.run
    try:
        branches = tuple((run.home / INTEGRATION).read_text().split())
    except OSError:
        branches = ()
    try:
        for line in follow_ups(run.state, branches, run.user):
            run.say(f"queue {run.project.name}: {line}")
    except Refused:
        return


INTEGRATION = "integration"
STEPS = (verbs.Step("before-watch", 8, "queue.follow_ups", _follow_ups),)


def hold(state: Path, slug: str) -> str:
    """Take the row's go back, and return the line that says what was held."""
    return _run(state, [(0, Hold(slug))])[0]


def remove(state: Path, slug: str, by: str, at: str, user: jsettings.Settings, asks: Asks) -> str:
    """Take the row out for good, and return the line that says what was done."""
    return _run(state, [(0, Remove(slug, by, at))], user, asks)[0]


def withdraw(
    state: Path, slug: str, why: str, at: str, by: str = WITHDRAWN_BY, asks: Asks | None = None
) -> str:
    """Take out a row that never launched (no thread, and at `queued` or `gate`, held or not)
    whose work is no longer there to do, and return the line that says so. `by` is who takes it
    out: jbus, on no one's word, or the home that ran `jbus queue withdraw`. `why` goes into its
    line of `transitions.jsonl` and into `removed.json`. A row that launched, or that another row
    waits on, is refused."""
    return _run(state, [(0, Withdraw(slug, why, at, by))], asks=asks)[0]


def rename(state: Path, slug: str, new: str, at: str, by: str, asks: Asks | None = None) -> str:
    """Move a row that never launched, and that no other row names, to the slug `new`, keeping
    its priority, depends, merge_after, entry and go, and return the line that says so."""
    return _run(state, [(0, Rename(slug, new, at, by))], asks=asks)[0]


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
      `--follows <parent slug>` (a `--rule <n>` beside it is taken and not read);
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
