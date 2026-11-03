from jbus.telemetry.kpis import Kpi, Lacks

KPI = Kpi(
    "Stall minutes per merged row",
    "speed",
    "minutes a running row was quiet or hung",
    "min",
    None,
    "lower",
    Lacks("a record of how long a row was quiet: hung.jsonl stopped on 2026-10-26"),
)
