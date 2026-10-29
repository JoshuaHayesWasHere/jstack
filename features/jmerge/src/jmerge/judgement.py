"""The two judgements jbus and `jmerge` both read, made here once: whether a queue row has a go
that holds for its brief (`has_go`), and the kind of a reason a pull request does not merge,
which says who lifts it (`lifted_by`), the word `jmerge` prints for it (`verb`) and the step jbus
shows it on (`step`).

A row's go is the user's (or the bot's, or a rule's) for the brief it was given for. jbus's
launch asks `approved_text` of a row and its stored brief, and `jmerge` asks `has_go` before it
merges, so a go that no longer holds stops both. jbus records the go (`jbus.queue.Approval`, a
`Go`); this module only reads it.

A reason on the `hold` step is one jbus shows as Needs you, waiting on the user's word. Each is
one a word of the user's lifts (`LIFTS`): `jbus queue approve` for the queue's own holds, since a
go is given in the queue and nowhere else, `/nohome merge on` for a repo whose merge the user
switched off, and `jmerge --accept` for every other, which `jmerge` therefore prints as `hold`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from jbriefs import meaning
from jmerge import ready

Row = dict[str, Any]

FINAL = ("merged", "done")
"""The statuses of a row that is over."""

SENT_TO = ("Home:", "Thread:", "Green main:", "Stacked on:")
"""The lines of a brief's head that a go does not cover: the first two name the threads that
receive the brief, and a launch writes the other two."""

HOLD = "hold"
ACCEPT = "jmerge --accept"
APPROVE = "jbus queue approve"
SWITCH = "/nohome merge on"
LIFTS = {ready.ROW_HELD.code: APPROVE, ready.NO_GO.code: APPROVE, ready.MERGE_OFF.code: SWITCH}
"""The holds that a word of the user's other than `--accept` lifts, by code, and that word."""


@dataclass(frozen=True)
class Go:
    """The record of a row's go, as jbus writes it (`jbus.queue.Approval` gives its fields'
    meaning). Here only `scope` and `meaning`, the fingerprint the go binds, are read."""

    basis: str
    ref: str
    words: str
    said_at: str
    said_in: str
    checked: bool
    ran_by: dict[str, str]
    ran_at: str
    follows: str = ""
    ground: str = ""
    brief_sha: str = ""
    scope: str = ""
    meaning: list[Any] = field(default_factory=list)
    message: str = ""
    closed_by: str = ""


def record[Kept: Go](row: Row, kind: type[Kept]) -> Kept | None:
    """Return the row's go as a record of `kind`, or None for a row with none or with a typed
    string."""
    try:
        return kind(**row["approval"]) if row.get("approval") else None
    except TypeError:
        return None


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def body(text: str) -> str:
    """Return the brief with no `SENT_TO` line in its head, the lines above its first `## `. A
    launch sends this text, so every line that a launch sends is a line that `brief_sha`
    covers."""
    kept, head = [], True
    for line in text.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(SENT_TO)):
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


def bound(row: Row) -> meaning.Meaning:
    """Return the fingerprint the row's go binds: its record's. Return nothing for a go bound only
    to a sha."""
    kept = record(row, Go)
    return kept.meaning if kept and kept.scope else []


def approved_text(row: Row, text: str) -> bool:
    """Return whether the row's go holds for the brief `text`.

    A go recorded with a fingerprint holds for every brief that means the same (`meaning.same`),
    whatever its wording. An older go holds only for the text the user approved: its row's
    `brief_sha`. For a row approved before `brief_sha` left out the two lines, it is the sha256 of
    the whole text, line for line.
    """
    kept = bound(row)
    if kept:
        return meaning.same(kept, fingerprint(text))
    return row.get("brief_sha") in (brief_sha(text), sha(text))


def has_go(row: Row, text: str | None) -> bool:
    """Return whether the row has a go that holds for its brief `text` as it stands: it is
    approved, its brief is there, and the go holds for it (`approved_text`). An `add` that changes
    a brief leaves `approved` set, so the flag alone is no go."""
    return bool(row.get("approved")) and text is not None and approved_text(row, text)


def lifted_by(why: str) -> str:
    """Return the word of the user's that lifts a reason: its own in `LIFTS`, `ACCEPT` for every
    other reason on the `hold` step, and nothing for a reason that is no hold."""
    code = ready.code_of(why)
    if ready.step_of(code) != HOLD:
        return ""
    return LIFTS.get(code, ACCEPT)


def verb(why: str) -> str:
    """Return the word `jmerge` prints for a pull request that does not merge for `why`: `hold`
    where `--accept` lifts it, `wait` otherwise."""
    return HOLD if lifted_by(why) == ACCEPT else "wait"


def step(said: str, code: str = "") -> str:
    """Return the step a pull request waits on, read from the last line `jmerge` printed about it
    (`<word>: <reason>`) and the reason's code where `merge.log` wrote one. A `hold` is on the
    `hold` step, and a `wait` is on the step of its code (`ready.step_of`). A line with no code,
    as `jmerge` prints it or as an older `merge.log` has it, takes the code its reason's text
    gives (`ready.code_of`). Return nothing for a line with no reason, or for a reason no rule
    names."""
    word, _, reason = said.partition(": ")
    if not reason:
        return ""
    if word == HOLD:
        return HOLD
    return ready.step_of(code or ready.code_of(reason))
