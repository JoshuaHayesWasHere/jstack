from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Redo rate",
    "quality",
    "merged rows a later row fixes or reverts within 7 days: a revert jbus opened, a "
    "main-red fix, or a follow-up queued after the merge; each row in the week its 7 days "
    "end, of those whose 7 days ended by the last build",
    "%",
    5,
    "lower",
    Measured(
        "weekly_redo",
        "rate",
        "judged",
        since="redo_since",
        records="the parents named by follow-ups' goes",
        detail="waiting || ' merged row' || CASE waiting WHEN 1 THEN '' ELSE 's' END "
        "|| ' not yet judged'",
    ),
)
