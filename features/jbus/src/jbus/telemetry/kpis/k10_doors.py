from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Doors opened without your own word",
    "safety",
    "door acts done by a home, a bot or jbus, not by you",
    "",
    0,
    "lower",
    Measured("weekly_doors", "not_yours", "done", empty=0),
)
