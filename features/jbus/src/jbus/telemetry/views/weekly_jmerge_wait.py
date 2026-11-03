"""Each week's waits for `jmerge`, of `jmerge_waits`: the median and the 85th percentile, in
minutes."""

from jbus.telemetry.schema import quantiles

SQL = quantiles("jmerge_waits", "minutes")
