from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="dollars-per-row",
    group="cost",
    says="dollars per row merged this week, at API list prices",
    unit="$",
    better="lower",
    source=Sql(
        "select dollars_per_row as value, rows as n from weekly_row_spend"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=7.06,
    baseline_of="last week's weekly_row_spend, the week of 2026-11-01",
    kind=Limit(8.47, 5),
    tier="page",
)
