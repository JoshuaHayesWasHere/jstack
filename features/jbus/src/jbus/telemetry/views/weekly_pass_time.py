"""Each week's seconds of a jbus pass, of `pass_times`: the median and the 85th percentile."""

from jbus.telemetry.schema import quantiles

SQL = quantiles("pass_times", "seconds")
