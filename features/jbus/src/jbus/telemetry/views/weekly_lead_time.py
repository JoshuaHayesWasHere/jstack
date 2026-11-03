"""Each week's lead time of `lead_times` (S5): the median and the 85th percentile, as
`statistics.median` and the scorecard's `pct` take them (`jbus.telemetry.schema.quantiles`)."""

from jbus.telemetry.schema import quantiles

SQL = quantiles("lead_times", "minutes")
