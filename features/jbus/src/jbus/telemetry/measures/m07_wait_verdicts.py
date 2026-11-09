from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="wait-verdicts",
    group="flow",
    says="jmerge wait verdicts per pull request it waited on, this week",
    unit="verdicts",
    better="lower",
    source=Sql(
        "select 1.0 * count(*) / nullif(count(distinct number), 0) as value,"
        " count(distinct number) as n from merges"
        " where project = :project and verb = 'wait' and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=9.0,
    baseline_of="the audit of 2026-11-09: 9.0 to 9.3",
    kind=Limit(10.8, 5),
    tier="page",
    audit=(37,),
)
