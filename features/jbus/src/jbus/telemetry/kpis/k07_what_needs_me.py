from jbus.telemetry.kpis import Kpi, Lacks

NO_TEXT = "the store keeps no text of a message (2026-11-02)"

KPI = Kpi(
    "'What needs me' asks",
    "attention",
    "times you asked what needs you",
    "",
    0,
    "lower",
    Lacks(
        "a label of what each message asks, recorded as it is written: the ask ledger "
        f"joins a message to its row, answer or reply, not to what it asked; {NO_TEXT}"
    ),
)
