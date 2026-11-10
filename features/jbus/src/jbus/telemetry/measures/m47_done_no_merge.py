from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="done-no-merge",
    group="cost",
    says="crew units this week on rows that ended done with no merge, per 72 h, in millions",
    unit="M units per 72 h",
    better="lower",
    source=Sql(
        "select coalesce(sum(c.units), 0) / 1e6 * 3.0"
        " / max(1.0, julianday(:ends) - julianday(:begins)) as value,"
        " count(distinct c.slug) as n from call_rows c"
        " join queue q on q.project = c.project and q.slug = c.slug"
        " where c.project = :project and c.role = 'crew' and q.status = 'done'"
        " and c.at >= :begins and c.at < :ends"
        " and not exists (select 1 from merged m where m.project = c.project and m.slug = c.slug)"
    ),
    window="week",
    baseline=53.4,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(64.1, 0),
    tier="page",
    audit=(20,),
)
