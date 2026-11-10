from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="closed-unmerged",
    group="cost",
    says=(
        "pull requests closed with no merge in the last 72 h where a row asked for one, no"
        " probe whose row asked for none and no revert of jbus's"
    ),
    unit="per 72 h",
    better="lower",
    source=Sql(
        "select count(*) as value, count(*) as n from ci_prs c"
        " where c.project = :project and c.merged is null"
        " and c.closed >= :begins and c.closed < :ends"
        " and not exists (select 1 from row_outcomes o where o.project = c.project"
        " and o.slug = c.branch and o.outcome = 'no pull request asked')"
        " and not exists (select 1 from reverts r where r.project = c.project"
        " and r.branch = c.branch)"
    ),
    window="72h",
    baseline=3,
    baseline_of="the audit of 2026-11-09, its 3 abandoned rows",
    kind=Limit(3.6, 0),
    tier="page",
    audit=(24,),
)
