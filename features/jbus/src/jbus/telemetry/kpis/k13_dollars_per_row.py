from jbus.telemetry.kpis import Kpi, Measured
from jgauge import spend

KPI = Kpi(
    "Dollars per merged row",
    "cost",
    f"an estimate at API list prices, from jgauge.spend's price table of {spend.PRICED_ON}: "
    "the dollars of a merged row's own threads, over the week's merged rows with any call "
    "recorded; a cache write at the one-hour price, and a call of a model the table does not "
    "price, every Codex model's, adds no dollars",
    "$",
    None,
    "lower",
    Measured("weekly_row_spend", "dollars_per_row", "rows"),
)
