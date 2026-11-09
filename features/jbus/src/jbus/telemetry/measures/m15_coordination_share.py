from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="coordination-share",
    group="cost",
    says="share of this week's spend on jbus sends and homes, of the days the spend records hold",
    unit="%",
    better="lower",
    source=Sql(
        "select coordination as value, days as n from weekly_spend"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=41.2,
    baseline_of="last week's weekly_spend, the week of 2026-11-01",
    kind=Limit(49.5, 3),
    tier="page",
    audit=(6,),
)
