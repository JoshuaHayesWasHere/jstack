"""`runs.jsonl` (`jbus.history`), each state a workflow run was seen in."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "run": _number(one.get("run")),
        "attempt": _number(one.get("attempt")),
        "workflow": _text(one.get("workflow")),
        "sha": _text(one.get("sha")),
        "branch": _text(one.get("branch")),
        "event": _text(one.get("event")),
        "pr": _number(one.get("pr")),
        "created": utc(one.get("created"), zone),
        "started": utc(one.get("started"), zone),
        "updated": utc(one.get("updated"), zone),
        "conclusion": _text(one.get("conclusion")),
    }


SOURCE = Source(
    "runs",
    "runs.jsonl",
    "log",
    _columns(
        "at",
        "run",
        "attempt",
        "workflow",
        "sha",
        "branch",
        "event",
        "pr",
        "created",
        "started",
        "updated",
        "conclusion",
    ),
    row,
    at="updated",
)
