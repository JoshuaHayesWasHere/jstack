"""Each week's last run of the drift probes, of `drift_runs`: the week's end (S4). A week is read
from its last run alone, so a week with no run has no data."""

SQL = (
    "SELECT week, at, probes, broken, unrun FROM (SELECT *, row_number() OVER "
    "(PARTITION BY week ORDER BY at DESC) AS place FROM drift_runs) WHERE place = 1"
)
