"""`main-reds.jsonl`, why main went red: one line for each tip `jbus.mainmoved.tell` judged
`failed`, with its verdict (`mainmoved.Verdict`), and one when a spell ends, at its first red tip,
with its `cause` (`mainmoved.closing_line`) and no verdict."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _count, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    prs = one.get("prs") if isinstance(one.get("prs"), list) else []
    return {
        "at": utc(one.get("at"), zone),
        "sha": _text(one.get("sha")),
        "pr": _number(prs[0]) if prs else None,
        "step": _text(one.get("step")),
        "tests": _count(one.get("failed")),
        "verdict": _text(one.get("verdict")),
        "cause": _text(one.get("cause")),
    }


SOURCE = Source(
    "main_reds",
    "main-reds.jsonl",
    "log",
    _columns("at", "sha", "pr", "step", "tests", "verdict", "cause"),
    row,
)
