from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Spend per merged row (M units)",
    "cost",
    "jgauge spend units of a merged row's own threads, of every provider, over the "
    "week's merged rows with any call recorded",
    "M",
    None,
    "lower",
    Measured("weekly_row_spend", "per_row", "rows"),
)
