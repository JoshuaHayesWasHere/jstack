"""`ci-prs.jsonl`, a snapshot of each pull request the CI ledger saw, by its number."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _count, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "number": _number(one.get("number")),
        "branch": _text(one.get("branch")),
        "head": _text(one.get("head")),
        "created": utc(one.get("created"), zone),
        "updated": utc(one.get("updated"), zone),
        "merged": utc(one.get("merged"), zone),
        "closed": utc(one.get("closed"), zone),
        "merge_commit": _text(one.get("merge_commit")),
        "pushes": _count(one.get("pushes")),
    }


SOURCE = Source(
    "ci_prs",
    "ci-prs.jsonl",
    "snapshot",
    _columns(
        "number",
        "branch",
        "head",
        "created",
        "updated",
        "merged",
        "closed",
        "merge_commit",
        "pushes",
    ),
    row,
    at="created",
    natural="number",
)
