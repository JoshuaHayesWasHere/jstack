"""The machine's `health.jsonl`, each reading of jbus's health look on a change or each 5
minutes (`jbus.health.keep`)."""

from __future__ import annotations

from jbus.telemetry import machine
from jbus.telemetry.records import Source
from jbus.telemetry.values import _columns

SOURCE = Source(
    "health_readings",
    "health.jsonl",
    "log",
    _columns("at", "reading", "value", "over"),
    machine.health_readings,
    where="machine",
)
