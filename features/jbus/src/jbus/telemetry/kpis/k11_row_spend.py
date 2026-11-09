from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Spend per merged row (M units)",
    "cost",
    "jgauge spend units of a merged row, of every provider: its own threads', the home turns "
    "that led to it, and its scout's even share over its plan entry's merged rows, over the "
    "week's merged rows with any call recorded",
    "M",
    None,
    "lower",
    Measured("weekly_row_spend", "per_row", "rows"),
)
