from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Redo rate",
    "quality",
    "merged rows a later row fixes or reverts within 7 days",
    "%",
    5,
    "lower",
    Lacks("a record of the merged row a later row fixes or reverts: no record names it"),
)
