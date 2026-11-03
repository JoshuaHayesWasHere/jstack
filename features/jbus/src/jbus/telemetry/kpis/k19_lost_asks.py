from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Lost asks (S3)",
    "attention",
    "asks of yours with no row, answer or reply",
    "",
    0,
    "lower",
    Measured("weekly_lost_asks", "lost", "typed", empty=0),
)
