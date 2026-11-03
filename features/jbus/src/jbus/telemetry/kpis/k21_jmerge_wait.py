from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Waiting for jmerge, PR p50 minutes",
    "speed",
    "minutes a green pull request waits for jmerge",
    "min",
    0.25,
    "lower",
    Lacks("jmerge's waits in seconds: merge.log stamps minutes, not when a blocker cleared"),
)
