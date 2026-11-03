from jbus.telemetry.kpis import ROWS, Kpi, Measured

KPI = Kpi(
    "Lead time, go to merge, median (DORA)",
    "speed",
    "minutes from a row's go to its merge (S5)",
    "min",
    30,
    "lower",
    Measured("weekly_lead_time", "median", "n", since="rows_since", records=ROWS),
)
