from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="hours-after-pr",
    group="flow",
    says="share of the row-hours of the rows merged this week spent with the pull request open",
    unit="%",
    better="lower",
    source=Sql(
        "with t as (select slug, to_status, at,"
        " lead(at) over (partition by slug order by at, key) as nx"
        " from transitions where project = :project),"
        " m as (select slug, merged_at from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends),"
        " h as (select to_status,"
        " (julianday(min(coalesce(nx, merged_at), merged_at)) - julianday(at)) * 24 as hours"
        " from t join m using (slug) where at < merged_at)"
        " select 100.0 * sum(case when to_status = 'pr' then hours end) / sum(hours) as value,"
        " (select count(*) from m) as n from h"
    ),
    window="week",
    baseline=52,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(62.4, 5),
    tier="page",
    audit=(4,),
)
