from jbus.telemetry.kpis import ROWS, Kpi, Measured

KPI = Kpi(
    "Your typed messages per merged row",
    "attention",
    "messages you typed, not resume clicks, over rows merged in the week",
    "",
    0.5,
    "lower",
    Measured("weekly_typed_per_row", "per_row", "merged", since="rows_since", records=ROWS),
)
