"""Each week's last run of the drift probes, of `drift_runs`: the week's end (S4). Only a week's
last run counts, so a week with no run has no data."""

SQL = (
    "SELECT project, week, at, probes, broken, unrun FROM (SELECT *, row_number() OVER "
    "(PARTITION BY project, week ORDER BY at DESC) AS place FROM drift_runs) WHERE place = 1"
)
