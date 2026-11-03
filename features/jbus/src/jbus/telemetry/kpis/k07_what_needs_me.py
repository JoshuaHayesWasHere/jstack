from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "'What needs me' asks",
    "attention",
    "messages you typed that ask what needs you, by one pattern, as they were read",
    "",
    0,
    "lower",
    Measured("weekly_needs_asks", "asks", "typed", empty=0),
)
