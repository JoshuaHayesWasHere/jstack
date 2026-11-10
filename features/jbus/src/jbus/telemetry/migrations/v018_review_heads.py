"""The head each reviewer thread was launched at, as `review-launches.jsonl` holds it
(`jbus.reviewlaunch`)."""

from jbus.telemetry.migrations import tables

SQL = tables("review_heads")
