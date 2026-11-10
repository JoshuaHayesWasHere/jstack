"""The rows of the machine's own logs, in jbus's state directory, whose rows are under the project
`values.MACHINE`: `passes.jsonl`, each pass and the seconds of its steps (`jbus.record`),
`drift.jsonl`, each probe of a standing word (`jbus.drift`), `capped.jsonl`, each read of
which instances are capped (`jgauge.limits.note`), and `health.jsonl`, each reading of the
health look (`jbus.health.keep`). `jbus.telemetry.records` names their sources.
"""

from __future__ import annotations

import json
from datetime import tzinfo

from jbus.telemetry.values import Row, _count, _dict, _number, _text, utc


def _seconds(given: object) -> float | None:
    return given if isinstance(given, int | float) and not isinstance(given, bool) else None


def passes(one: Row, zone: tzinfo | None) -> Row:
    """A pass: its seconds, the CPU seconds of its children, and `step_times`, each step's
    `[wall, cpu]` as JSON, which the view `pass_steps` reads a row a step. A step whose figures
    are not two numbers is left out."""
    steps = {
        name: [_seconds(took[0]), _seconds(took[1])]
        for name, took in sorted(_dict(one.get("steps")).items())
        if isinstance(took, list) and len(took) == 2 and None not in map(_seconds, took)
    }
    return {
        "at": utc(one.get("at"), zone),
        "seconds": _seconds(one.get("seconds")),
        "step_times": json.dumps(steps) if steps else None,
        "children": _seconds(one.get("children")),
    }


def drift(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "probe": _text(one.get("probe")),
        "word": _text(one.get("word")),
        "status": _text(one.get("status")),
        "found": _number(one.get("found")),
        "sha": _text(one.get("sha")),
        "error": _text(one.get("error")),
    }


def capped_reads(one: Row, zone: tzinfo | None) -> Row:
    """A read of which instances the ledger has capped (`jgauge.limits.note`): how many it read,
    how many were capped, and, where every one was, `ends_at`, the first time one is free again."""
    instances, capped = one.get("instances"), _dict(one.get("capped"))
    count = _count(instances)
    frees = [found for found in (utc(at) for at in capped.values()) if found is not None]
    every = bool(count) and len(frees) == len(capped) >= count
    return {
        "at": utc(one.get("at"), zone),
        "reader": _text(one.get("reader")),
        "instances": count,
        "capped": len(capped),
        "ends_at": min(frees) if every else None,
    }


def health_readings(one: Row, zone: tzinfo | None) -> Row:
    """A reading of jbus's health look (`jbus.health.keep`): its key as `reading`, since `key` is
    each table's own, its number, and whether it was over its limit, None where the look could
    not read it."""
    over, value = one.get("over"), one.get("value")
    return {
        "at": utc(one.get("at"), zone),
        "reading": _text(one.get("key")),
        "value": value if isinstance(value, int | float) and not isinstance(value, bool) else None,
        "over": over if isinstance(over, bool) else None,
    }
