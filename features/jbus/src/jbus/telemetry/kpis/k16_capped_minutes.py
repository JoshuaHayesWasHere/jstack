from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Capped minutes (every instance capped)",
    "reliability",
    "minutes a day with every agent instance capped",
    "min",
    0,
    "lower",
    Lacks("a record of capped spells: the limits files hold the current value only"),
)
