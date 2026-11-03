"""Each merged pull request's wait for `jmerge` from ready to its merge, to the second, with the
codes that held it (`merge-waits.jsonl`, `jmerge.waits`)."""

from jbus.telemetry.migrations import tables

SQL = tables("merge_waits")
