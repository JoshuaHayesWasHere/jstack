from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Waiting for jmerge, PR p50 minutes",
    "speed",
    "minutes from the second a pull request's required checks passed at the head it merged at to "
    "the second jmerge began its merge, by jmerge's record of each wait, or before it by the last "
    "passed check to GitHub's merge time",
    "min",
    0.25,
    "lower",
    Measured("weekly_jmerge_wait", "median", "n"),
)
