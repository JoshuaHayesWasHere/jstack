from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Gates closed by silence that were wrong (S8)",
    "attention",
    "closes by silence later corrected, over closes with a known outcome",
    "%",
    5,
    "lower",
    Lacks("a scout's labels each week (gate-labels)"),
)
