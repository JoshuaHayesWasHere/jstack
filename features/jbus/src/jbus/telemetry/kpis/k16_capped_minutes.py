from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Capped minutes (every instance capped)",
    "reliability",
    "minutes of the week with every agent instance capped, by the ledger, read each "
    "minute by jbus's pass and each 2 by jgauge limits",
    "min",
    0,
    "lower",
    Measured(
        "weekly_capped",
        "minutes",
        "reads",
        since="capped_since",
        records="the reads of which instances are capped",
        partial=True,
    ),
)
