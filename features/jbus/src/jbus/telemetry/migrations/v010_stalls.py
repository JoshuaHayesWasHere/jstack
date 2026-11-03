"""Each spell a running row's thread was quiet or hung (`stalls.jsonl`, `jbus.stall.spells`)."""

from jbus.telemetry.migrations import tables

SQL = tables("stalls")
