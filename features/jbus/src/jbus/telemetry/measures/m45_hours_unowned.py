from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="hours-unowned",
    group="flow",
    says=(
        "hours the rows merged in the last 72 h sat in waiting or left, but left for the review"
        " before their pull request, which its reviewer owns"
    ),
    unit="h per 72 h",
    better="lower",
    source=Sql(
        "with t as (select slug, to_status, at,"
        " lead(at) over (partition by slug order by at, key) as nx,"
        " lead(to_status) over (partition by slug order by at, key) as then_status"
        " from transitions where project = :project),"
        " m as (select slug, merged_at from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends)"
        " select coalesce(sum(case when to_status = 'waiting'"
        " or (to_status = 'left' and coalesce(then_status, '') != 'pr') then"
        " (julianday(min(coalesce(nx, merged_at), merged_at)) - julianday(at)) * 24 end), 0)"
        " as value, (select count(*) from m) as n from t join m using (slug) where at < merged_at"
    ),
    window="72h",
    baseline=68.7,
    baseline_of="the audit of 2026-11-09: 44.6 to 68.7 h per 72 h",
    kind=Limit(82.4, 5),
    tier="page",
    audit=(12,),
)
