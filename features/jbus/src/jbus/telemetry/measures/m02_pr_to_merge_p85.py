from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="pr-to-merge-p85",
    group="flow",
    says="minutes from a pull request's opening to its merge, 85th percentile, this week",
    unit="min",
    better="lower",
    source=Sql(
        "select p85 as value, n from weekly_pr_to_merge"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=261,
    baseline_of="last week's weekly_pr_to_merge, the week of 2026-11-01",
    kind=Limit(313.2, 5),
    tier="page",
    audit=(2,),
)
