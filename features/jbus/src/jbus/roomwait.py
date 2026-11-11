"""The reason a row waits for room on the machine, kept to what holds while the wait lasts.

`jgauge room` says why it has no room with the reading of the moment, as `load 30.00 is at or
over 200% of 12 cores; the busiest: ...`. A row's reason is what `queue.derive` compares from
pass to pass: a new one writes a `waits.jsonl` line and starts the row's `since` again. So the
reason keeps the head of what `jgauge room` said, the thing it waits on and its limit, and drops
the reading: one wait on load stays one reason while the load moves.
"""

from __future__ import annotations

import re

ROOM = "waiting for room on the machine"
"""The start of a row's reason where `jgauge room` said no for all but a full /tmp (which
`cleanup.waiting` names), followed by the head of what it said (`reason`), as `waiting for room on
the machine: load is at or over 85% of 12 cores`: each reader reads it as room by its start, the
store its cause."""

HEADS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"load \S+ (is at or over \S+ of \S+ cores)\b"), r"load \1"),
    (re.compile(r"CPU pressure \S+ (is at or over \S+)$"), r"CPU pressure \1"),
    (re.compile(r"\S+ GB of memory available, (under \S+)$"), r"memory available \1 GB"),
    (re.compile(r"memory pressure \S+ (is at or over \S+)$"), r"memory pressure \1"),
    (
        re.compile(r"the (\S+) limit is \S+% used, (at or over \S+%), and resets in "),
        r"the \1 limit is \2",
    ),
    (re.compile(r"(.+ are (both|all) at or over \S+%): "), r"\1"),
    (
        re.compile(
            r".+ could not be read$"
            r"|jgauge room did not run$"
            r"|.+ is not a pool of provider instances$"
        ),
        r"\g<0>",
    ),
)
"""Each no of `jgauge room` that jbus knows, and the head its reason keeps: what it waits on and
the limit, never the reading. A no that none matches keeps no head, since its text may carry a
reading."""


def reason(why: str) -> str:
    """The reason a row waits when `jgauge room` said `why`: `ROOM`, and the head of `why` after
    it where `HEADS` knows its shape."""
    for pattern, head in HEADS:
        if found := pattern.match(why):
            return f"{ROOM}: {found.expand(head)}"
    return ROOM
