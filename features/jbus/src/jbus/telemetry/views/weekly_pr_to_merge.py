"""Each week's minutes from a pull request's opening to its merge, of `pr_times`: the median and the
85th percentile."""

from jbus.telemetry.schema import quantiles

SQL = quantiles("pr_times", "minutes")
