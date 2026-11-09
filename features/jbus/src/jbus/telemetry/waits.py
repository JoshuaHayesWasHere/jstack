"""The kind of reason a row waits, as the one label the store keeps of it (`row_waits`): the
reason's text, which `jbus.watch.why` and `jbus.dispatch` write, is read by its start. A row waits
on a slug it `depends` on, on a `red main`, on a `cap` of jbus's config, on `room` on the machine
or for a crew model, or on the user (`hold`). A row with no reason, or one this table does not
know, is `none`.
"""

from __future__ import annotations

import re
from datetime import tzinfo

from jbus.telemetry.values import Row, _length, _text, utc

KINDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("depends", r"depends on "),
        ("red main", r"main is red"),
        ("cap", r"max_(per_home|per_project|running) is "),
        ("room", r"waiting(: \S+ at \d+% of its | for room )|no launch: "),
        (
            "hold",
            r"not approved$|brief changed after approval|a gate |check failed twice$"
            r"|dispatch is off$|the stop file is there$|your go was taken back"
            r"|waits for the user's go|main is green again at ",
        ),
    )
)


def kind(why: str) -> str:
    return next((name for name, pattern in KINDS if pattern.match(why)), "none")


def row(one: Row, zone: tzinfo | None) -> Row:
    """A line of `waits.jsonl` as its row of `row_waits`: the reason's kind and length, no text."""
    why = one.get("why")
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "kind": kind(why if isinstance(why, str) else ""),
        "why_len": _length(why),
    }
