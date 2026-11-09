from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="pr-checks-failed",
    group="quality",
    says="share of today's check runs on pull requests that failed",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(conclusion = 'failure') / nullif(count(*), 0) as value, count(*) as n"
        " from runs where project = :project and workflow = 'check' and event = 'pull_request'"
        " and created >= :begins and created < :ends"
    ),
    window="day",
    baseline=33.8,
    baseline_of="the audit of 2026-11-09: 33.8 to 48%; 5.4% on 2026-11-05",
    kind=Limit(30, 10),
    tier="wake",
    audit=(29,),
)
