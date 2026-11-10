"""`reverts.json`, a snapshot of each revert jbus opened (`jmerge.reverts`), by its red tip."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.readers import keyed
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _pull, _text


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "red": _text(one.get("red")),
        "slug": _text(one.get("slug")),
        "branch": _text(one.get("branch")),
        "pr": _pull(one.get("pull")),
    }


SOURCE = Source(
    "reverts",
    "reverts.json",
    "snapshot",
    _columns("red", "slug", "branch", "pr"),
    row,
    at="",
    records=keyed("red"),
    natural="red",
)
