"""`review-rounds.jsonl` (`jbus.reviewed`), each round of a review, with its findings by
severity."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import SEVERITIES, Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "pr": _number(one.get("pr")),
        "round_number": _number(one.get("round")),
        "head": _text(one.get("head")),
        "scoped": one.get("scoped") if isinstance(one.get("scoped"), bool) else None,
        "sections": _number(one.get("sections")),
        "meets": _text(one.get("meets")),
        "met": _number(one.get("met")),
        "done_when": _number(one.get("of")),
        **{name: _number(one.get(name)) for name in SEVERITIES},
    }


SOURCE = Source(
    "review_rounds",
    "review-rounds.jsonl",
    "log",
    _columns(
        "at",
        "slug",
        "pr",
        "round_number",
        "head",
        "scoped",
        "sections",
        "meets",
        "met",
        "done_when",
        *SEVERITIES,
    ),
    row,
)
