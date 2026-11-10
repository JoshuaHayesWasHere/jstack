from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="brief-versions",
    group="quality",
    says="share of the briefs written this week that have two or more versions",
    unit="%",
    better="lower",
    source=Sql(
        "with b as (select slug, count(*) as k from brief_versions"
        " where project = :project and at >= :begins and at < :ends group by slug)"
        " select 100.0 * sum(k >= 2) / nullif(count(*), 0) as value, count(*) as n from b"
    ),
    window="week",
    baseline=17,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(20.4, 10),
    tier="page",
    audit=(38,),
)
