from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="typed-per-row",
    group="attention",
    says="messages the user typed this week per row merged this week",
    unit="per row",
    better="lower",
    source=Sql(
        "select per_row as value, merged as n from weekly_typed_per_row"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=1.07,
    baseline_of="last week's weekly_typed_per_row, the week of 2026-11-01",
    kind=Limit(1.28, 5),
    tier="page",
)
