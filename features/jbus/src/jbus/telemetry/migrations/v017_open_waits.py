"""Each ready pull request still open and the spell of its wait for `jmerge`, as the home's
`merge-waits.json` holds it now (`jmerge.waits`)."""

from jbus.telemetry.migrations import tables

SQL = tables("open_waits")
