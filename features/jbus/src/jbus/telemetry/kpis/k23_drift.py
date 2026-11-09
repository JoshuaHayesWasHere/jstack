from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Drift: standing words broken (S4)",
    "attention",
    "probed standing words not held, broken or unrun, in the week's last daily run",
    "",
    0,
    "lower",
    Measured("weekly_drift", "broken", "probes", machine=True),
)
