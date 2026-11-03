from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Coordination share of spend",
    "cost",
    "jbus sends and homes over all spend, of the runs jgauge spend counts",
    "%",
    20,
    "lower",
    Measured("weekly_spend", "coordination", "days"),
)
