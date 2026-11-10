"""`ci.jsonl`, the CI ledger: each job of each run, by when it was created."""

from __future__ import annotations

from datetime import tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import Row, _columns, _count, _number, _text, utc


def row(one: Row, zone: tzinfo | None) -> Row:
    return {
        "run": _number(one.get("run")),
        "job": _number(one.get("job")),
        "attempt": _number(one.get("attempt")),
        "name": _text(one.get("name")),
        "sha": _text(one.get("sha")),
        "branch": _text(one.get("branch")),
        "pr": _number(one.get("pr")),
        "event": _text(one.get("event")),
        "created": utc(one.get("created"), zone),
        "started": utc(one.get("started"), zone),
        "completed": utc(one.get("completed"), zone),
        "conclusion": _text(one.get("conclusion")),
        "runner": _text(one.get("runner")),
        "kind": _text(one.get("kind")),
        "steps": _number(one.get("steps")),
        "selection": _text(one.get("selection")),
        "slowest_s": one.get("slowest_s")
        if isinstance(one.get("slowest_s"), int | float)
        else None,
        "tail_s": one.get("tail_s") if isinstance(one.get("tail_s"), int | float) else None,
        "workers": _number(one.get("workers")),
        "tests": _count(one.get("tests")),
        "signs": _count(one.get("signs")),
        "step": _text(one.get("step")),
    }


SOURCE = Source(
    "ci_jobs",
    "ci.jsonl",
    "log",
    _columns(
        "run",
        "job",
        "attempt",
        "name",
        "sha",
        "branch",
        "pr",
        "event",
        "created",
        "started",
        "completed",
        "conclusion",
        "runner",
        "kind",
        "steps",
        "selection",
        "slowest_s",
        "tail_s",
        "workers",
        "tests",
        "signs",
        "step",
    ),
    row,
    at="created",
)
