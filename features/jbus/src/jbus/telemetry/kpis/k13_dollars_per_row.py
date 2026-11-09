from jbus.telemetry.kpis import Aside, Kpi, Measured
from jgauge import spend

KPI = Kpi(
    "Dollars per merged row",
    "cost",
    f"an estimate at API list prices, from jgauge.spend's price table of {spend.PRICED_ON}: "
    "the dollars of a merged row: its own threads', the home turns that led to it, and its "
    "scout's even share over its plan entry's merged rows, over the week's merged rows with any "
    "call recorded; a cache write at the one-hour price, and a call of a model the table does not "
    "price, every Codex model's, adds no dollars, and a week names each model of the provider "
    "it prices that it lacks",
    "$",
    None,
    "lower",
    Measured(
        "weekly_row_spend",
        "dollars_per_row",
        "rows",
        aside=Aside("weekly_unpriced", "no price in jgauge.spend's table for", "call"),
    ),
)
