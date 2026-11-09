from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="follow-ups",
    group="quality",
    says="follow-up, main-red and revert rows this week, per row merged this week",
    unit="per row",
    better="lower",
    source=Sql(
        "select 1.0 * (select count(*) from redos"
        " where project = :project and at >= :begins and at < :ends)"
        " / nullif(count(*), 0) as value, count(*) as n from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends"
    ),
    window="week",
    baseline=0.30,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(0.36, 10),
    tier="page",
    audit=(33,),
)
