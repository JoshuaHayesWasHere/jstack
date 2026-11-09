"""Each change of a row's reason to wait (`waits.jsonl`, `jbus.queue.derive`)."""

from jbus.telemetry.migrations import tables

SQL = tables("row_waits")
