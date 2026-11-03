from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Capped-failure share of spend",
    "reliability",
    "spend of runs that failed on a usage limit or part way, over all spend, of the runs "
    "jgauge spend counts",
    "%",
    1,
    "lower",
    Measured("weekly_spend", "capped", "days"),
)
