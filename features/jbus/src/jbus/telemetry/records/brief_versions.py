"""`brief-versions.jsonl` (`jbus.history`), each version of a brief, with what its `Pull request:`
line asks and how its last Result ended the row (`jbus.outcome`)."""

from __future__ import annotations

from datetime import tzinfo
from pathlib import Path

from jbus import history, outcome
from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "sha": _text(one.get("sha")),
        "was": _text(one.get("was")),
        "bytes": _number(one.get("bytes")),
        "pull": _text(one.get("pull")),
        "outcome": _text(one.get("outcome")),
    }


def _kept_pull(one: Row, beside: Path) -> Row:
    """A line written before `history.brief` wrote `pull`, with the `pull` of its version's text
    as `brief-versions/<sha>.md` keeps it, where that file is there: a line with neither keeps no
    `pull`, so it reads as empty, never as `none`."""
    sha = one.get("sha")
    if "pull" in one or not isinstance(sha, str) or not sha.isalnum():
        return one
    try:
        text = (beside / history.KEPT / f"{sha}.md").read_text(errors="replace")
    except OSError:
        return one
    return {**one, "pull": outcome.pull(text)}


SOURCE = Source(
    "brief_versions",
    "brief-versions.jsonl",
    "log",
    _columns("at", "slug", "sha", "was", "bytes", "pull", "outcome"),
    row,
    beside=_kept_pull,
)
