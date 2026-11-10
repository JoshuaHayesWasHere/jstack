from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
    audit=(4,),
)
