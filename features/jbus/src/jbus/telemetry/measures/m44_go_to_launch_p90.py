from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="go-to-launch-p90",
    group="flow",
    says="minutes from the go to a row's first launch, 90th percentile, of this week's merges",
    unit="min",
    better="lower",
    source=Sql(
        "with w as (select (julianday(l.at) - julianday(t.go)) * 1440 as minutes"
        " from lead_times t join row_moves l"
        " on l.project = t.project and l.slug = t.slug and l.to_status = 'launched'"
        " where t.project = :project and t.merged_at >= :begins and t.merged_at < :ends),"
        " r as (select minutes, row_number() over (order by minutes) as place,"
        " count(*) over () as n from w)"
        " select max(case when place - 1 = min(n - 1, cast(0.9 * n as integer))"
        " then minutes end) as value, coalesce(max(n), 0) as n from r"
    ),
    window="week",
    baseline=54.8,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(65.8, 10),
    tier="page",
    audit=(11,),
)
