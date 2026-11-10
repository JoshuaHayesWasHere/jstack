from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="two-review-rounds",
    group="quality",
    says="share of the rows merged this week that took two or more review rounds",
    unit="%",
    better="lower",
    source=Sql(
        "with m as (select slug from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends),"
        " r as (select slug, max(round_number) as rounds from review_rounds"
        " where project = :project and slug in (select slug from m) group by slug)"
        " select 100.0 * sum(rounds >= 2) / nullif(count(*), 0) as value, count(*) as n from r"
    ),
    window="week",
    baseline=46,
    baseline_of="the audit of 2026-11-09: 109 of 239",
    kind=Limit(55.2, 10),
    tier="page",
    audit=(7,),
)
