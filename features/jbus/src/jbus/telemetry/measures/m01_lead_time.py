from jbus.telemetry.measures import Limit, Measure, Sql

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
    baseline=105.9,
    baseline_of="last week's weekly_lead_time, the week of 2026-11-01",
    kind=Limit(127, 5),
    tier="page",
)
