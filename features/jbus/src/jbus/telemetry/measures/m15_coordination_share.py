from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 3),
    tier="page",
    audit=(6,),
)
