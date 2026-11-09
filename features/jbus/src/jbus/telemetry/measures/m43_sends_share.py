from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="sends-share",
    group="cost",
    says="share of this week's units spent on crew runs jbus sends started, of the days kept",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(coalesce(sends, 0)) / nullif(sum(units), 0) as value, count(*) as n"
        " from spend_kept where project = :project"
        " and spent_on >= date(:begins) and spent_on < date(:ends)"
    ),
    window="week",
    baseline=28.3,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(34, 3),
    tier="page",
    audit=(6,),
)
