from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Time to restore main, median (DORA)",
    "main",
    "minutes from a push check's first failure on main to its next pass (S7)",
    "min",
    15,
    "lower",
    Measured("weekly_restore", "median", "spells"),
)
