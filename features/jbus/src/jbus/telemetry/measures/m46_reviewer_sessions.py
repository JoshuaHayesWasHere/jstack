from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="reviewer-sessions",
    group="cost",
    says="reviewer sessions per row merged this week",
    unit="per row",
    better="lower",
    source=Sql(
        "with m as (select slug from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends)"
        " select 1.0 * (select count(distinct session) from call_rows"
        " where project = :project and role = 'reviewer' and slug in (select slug from m))"
        " / nullif(count(*), 0) as value, count(*) as n from m"
    ),
    window="week",
    baseline=1.6,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(1.92, 5),
    tier="page",
    audit=(14,),
)
