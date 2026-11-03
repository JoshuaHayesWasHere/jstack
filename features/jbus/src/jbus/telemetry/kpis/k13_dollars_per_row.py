from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Dollars per merged row",
    "cost",
    "billed dollars over rows merged",
    "$",
    None,
    "lower",
    Lacks("cost_usd from the agents' OpenTelemetry (design C) or a price table"),
)
