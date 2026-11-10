"""`merged.json`, a snapshot of each merged pull request, by its row's slug."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.readers import keyed
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _dict, _length, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "slug": _text(one.get("slug")),
        "number": _number(one.get("number")),
        "merged_at": utc(one.get("mergedAt"), zone),
        "merge_commit": _text(_dict(one.get("mergeCommit")).get("oid")),
        "state": _text(one.get("state")),
        "title_len": _length(one.get("title")),
    }


SOURCE = Source(
    "merged",
    "merged.json",
    "snapshot",
    _columns("slug", "number", "merged_at", "merge_commit", "state", "title_len"),
    row,
    at="merged_at",
    records=keyed("slug"),
    natural="slug",
)
