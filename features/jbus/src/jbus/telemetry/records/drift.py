"""The machine's `drift.jsonl` (`jbus.drift`), each probe of a standing word in each run."""

from __future__ import annotations

from jbus.telemetry import machine
from jbus.telemetry.records import Source
from jbus.telemetry.values import _columns

SOURCE = Source(
    "drift",
    "drift.jsonl",
    "log",
    _columns("at", "probe", "word", "status", "found", "sha", "error"),
    machine.drift,
    where="machine",
)
