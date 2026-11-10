from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="change-failure",
    group="quality",
    says="share of this week's merges that a follow-up, a revert or a red main redid",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * rate as value, merged as n from weekly_change_failure"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=3.0,
    baseline_of="last week's weekly_change_failure, the week of 2026-11-01",
    kind=Limit(3.6, 20),
    tier="page",
)
