from jbus.telemetry.kpis import ROWS, Covers, Kpi, Measured

KPI = Kpi(
    "Change failure rate, push checks (DORA)",
    "main",
    "merged rows whose pull request opened a red spell of main's push checks (S6), of the "
    "projects and days whose push checks the store keeps",
    "%",
    2,
    "lower",
    Measured(
        "weekly_change_failure",
        "100.0 * rate",
        "merged",
        covers=Covers("ci_projects", "ci_gaps", "push check of main"),
        since="rows_since",
        records=ROWS,
    ),
)
