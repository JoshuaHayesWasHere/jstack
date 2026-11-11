"""`waits.jsonl`, each wait of a row (`jbus.telemetry.waits`)."""

from __future__ import annotations

from jbus.telemetry import waits
from jbus.telemetry.records import Source
from jbus.telemetry.values import _columns

SOURCE = Source(
    "row_waits",
    "waits.jsonl",
    "log",
    _columns("at", "slug", "kind", "why_len", "launch_cause", "launch_reason"),
    waits.row,
)
