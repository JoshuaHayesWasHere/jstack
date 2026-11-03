from jbus.telemetry.kpis import Kpi, Measured

KPI = Kpi(
    "Crew first-round share",
    "quality",
    "merged pull requests with no red check and no wait on a crew's fix round, of those "
    "whose pull_request checks the CI ledger kept",
    "%",
    50,
    "higher",
    Measured(
        "weekly_first_round",
        "share",
        "n",
        since="fix_rounds_since",
        records="jmerge's waits labelled as a crew's fix round",
    ),
)
