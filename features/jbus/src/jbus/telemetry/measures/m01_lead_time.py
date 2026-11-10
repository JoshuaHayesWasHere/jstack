from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

MEASURE = Measure(
    name="lead-time",
    group="flow",
    says="minutes from the user's go to the merge, median, of the rows merged this week",
    unit="min",
    better="lower",
    source=Sql(
        "select median as value, n from weekly_lead_time"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
)
