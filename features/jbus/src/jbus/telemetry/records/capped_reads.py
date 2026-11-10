"""The machine's `capped.jsonl`, each read of which instances are capped (`jgauge.limits.note`)."""

from __future__ import annotations

from jbus.telemetry import machine
from jbus.telemetry.records import Source
from jbus.telemetry.values import _columns

SOURCE = Source(
    "capped_reads",
    "capped.jsonl",
    "log",
    _columns("at", "reader", "instances", "capped", "ends_at"),
    machine.capped_reads,
    where="machine",
)
