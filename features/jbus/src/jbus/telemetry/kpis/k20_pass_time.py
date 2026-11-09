from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "jbus pass, median seconds",
    "speed",
    "wall clock of one jbus pass",
    "s",
    30,
    "lower",
    Measured("weekly_pass_time", "median", "n", machine=True),
)
