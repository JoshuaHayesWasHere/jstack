from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="hours-unowned",
    group="flow",
    says="hours the rows merged this week sat in waiting or left, per 72 h of the week so far",
    unit="h per 72 h",
    better="lower",
    source=Sql(
        "with t as (select slug, to_status, at,"
        " lead(at) over (partition by slug order by at, key) as nx"
        " from transitions where project = :project),"
        " m as (select slug, merged_at from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends)"
        " select coalesce(sum(case when to_status in ('waiting', 'left') then"
        " (julianday(min(coalesce(nx, merged_at), merged_at)) - julianday(at)) * 24 end), 0)"
        " * 3.0 / max(1.0, julianday(:ends) - julianday(:begins)) as value,"
        " (select count(*) from m) as n from t join m using (slug) where at < merged_at"
    ),
    window="week",
    baseline=68.7,
    baseline_of="the audit of 2026-11-09: 44.6 to 68.7 h per 72 h",
    kind=Limit(82.4, 5),
    tier="page",
    audit=(12,),
)
