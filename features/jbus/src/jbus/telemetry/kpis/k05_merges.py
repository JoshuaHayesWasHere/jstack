from jbus.telemetry.kpis import ROWS, Kpi, Measured

KPI = Kpi(
    "Merges a week (DORA frequency)",
    "speed",
    "rows merged in the week",
    "",
    None,
    "higher",
    Measured("weekly_merges", "merged", "merged", empty=0, since="rows_since", records=ROWS),
)
