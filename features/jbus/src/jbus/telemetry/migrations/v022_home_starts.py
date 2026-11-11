"""Each failed home start `relaunches.json` names, with when it was launched
(`jbus.telemetry.records.home_starts`), which `launch_failures` reads."""

from jbus.telemetry.migrations import tables

SQL = tables("home_starts")
