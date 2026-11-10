from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
)
