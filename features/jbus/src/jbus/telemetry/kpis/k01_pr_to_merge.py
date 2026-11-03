from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "PR open to merge, median",
    "speed",
    "minutes from a pull request's opening to its merge, of those jmerge merged",
    "min",
    10,
    "lower",
    Measured("weekly_pr_to_merge", "median", "n"),
)
