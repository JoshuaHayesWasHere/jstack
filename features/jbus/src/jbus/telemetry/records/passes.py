"""The machine's `passes.jsonl` (`jbus.record`), the seconds of each pass, of each of its steps
and of its children."""

from __future__ import annotations

from jbus.telemetry import machine
from jbus.telemetry.records import Source
from jbus.telemetry.values import _columns

SOURCE = Source(
    "passes",
    "passes.jsonl",
    "log",
    _columns("at", "seconds", "step_times", "children"),
    machine.passes,
    where="machine",
)
