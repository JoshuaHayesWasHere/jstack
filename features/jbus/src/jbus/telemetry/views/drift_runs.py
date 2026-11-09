"""Each run of the drift probes (`jbus.drift`), all its lines under one `at`, with how many probes
it ran, those not held, broken or unrun, and those unrun (S4)."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT project, {WEEK.format(day='day')} AS week, at, count(*) AS probes, "
    "sum(status <> 'held') AS broken, sum(status = 'unrun') AS unrun FROM drift "
    "WHERE day IS NOT NULL GROUP BY 1, 2, at"
)
