from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="crew-after-pr",
    group="cost",
    says="share of the crew units of this week's merged rows spent after the pull request opened",
    unit="%",
    better="lower",
    source=Sql(
        "with m as (select slug, number from merged"
        " where project = :project and merged_at >= :begins and merged_at < :ends),"
        " c as (select c.units, c.at >= p.created as after from call_rows c"
        " join m on m.slug = c.slug"
        " join ci_prs p on p.project = c.project and p.number = m.number"
        " where c.project = :project and c.role = 'crew')"
        " select 100.0 * sum(case when after then units end) / nullif(sum(units), 0) as value,"
        " (select count(*) from m) as n from c"
    ),
    window="week",
    baseline=40,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(48, 5),
    tier="page",
    audit=(4,),
)
