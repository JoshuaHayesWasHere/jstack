from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
    audit=(2,),
)
