from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="go-refused",
    group="attention",
    says="share of this week's go acts jbus refused",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(outcome = 'refused') / nullif(count(*), 0) as value, count(*) as n"
        " from acts where project = :project and verb = 'go' and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=29,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(34.8, 10),
    tier="page",
    audit=(5,),
)
