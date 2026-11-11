"""Read a `Status:` line: a crew's Result, a scout's Report, a gate, or an old plan entry says
where it stands on one, and every reader turns it into a `Status` here, never by comparing the
words itself.

The line's first word decides it, as the scout skill's settle block reads it. `done` is done only
as a word of its own: `Status: done (both ran the same cases)` is done, and so is any note after a
space or a full stop, while `Status: done, mostly` and `Status: done: but` qualify it and are
`OTHER`, since done ends a row and its thread. The other words may carry a trailing `,`, `.`,
`:` or `;`, as the crew skill's End reads `paused`: `Status: paused, waits on a-b` is paused.
`not done` is two words. A line with no words, or no line, is `NONE`; any other word, `left`
included (a row's status, never a `Status:` line's), is `OTHER`.
"""

from __future__ import annotations

from enum import StrEnum

from jbriefs import below

LABEL = "Status:"


class Status(StrEnum):
    DONE = "done"
    NOT_DONE = "not done"
    BLOCKED = "blocked"
    PAUSED = "paused"
    OPEN = "open"
    ANSWERED = "answered"
    OTHER = "other"
    NONE = "none"


_WORDS = {Status.BLOCKED, Status.PAUSED, Status.OPEN, Status.ANSWERED}


def read(said: str) -> Status:
    """The `Status` of the words after `Status:`."""
    words = said.split()
    if not words:
        return Status.NONE
    first = words[0]
    if first in ("done", "done."):
        return Status.DONE
    if first == "not" and words[1:2] and words[1].rstrip(",.:;") == "done":
        return Status.NOT_DONE
    bare = first.rstrip(",.:;")
    return next((one for one in _WORDS if one.value == bare), Status.OTHER)


def of(text: str) -> Status:
    """The `Status` of the first `Status:` line of the text, `NONE` for text with none."""
    return read(below.line(text, LABEL))


def last(text: str) -> Status:
    """The `Status` of the last `Status:` line of the text, `NONE` for text with none."""
    said = [one for one in text.splitlines() if one.startswith(LABEL)]
    return read(said[-1].removeprefix(LABEL)) if said else Status.NONE
