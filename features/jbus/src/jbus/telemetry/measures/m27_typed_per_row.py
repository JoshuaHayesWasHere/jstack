from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
)
