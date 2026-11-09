from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="first-round",
    group="quality",
    says="share of this week's pull requests that merged on their first review round",
    unit="%",
    better="higher",
    source=Sql(
        "select share as value, n from weekly_first_round"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=29.9,
    baseline_of="last week's weekly_first_round, the week of 2026-11-01",
    kind=Limit(23.9, 5),
    tier="page",
    audit=(4,),
)
