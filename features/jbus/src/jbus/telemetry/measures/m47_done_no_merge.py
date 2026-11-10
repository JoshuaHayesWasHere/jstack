from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="done-no-merge",
    group="cost",
    says=(
        "crew units this week on rows that ended done with no merge and bought none: nothing to"
        " change, dropped, or ended with no outcome named (`row_outcomes`), per 72 h, in millions"
    ),
    unit="M units per 72 h",
    better="lower",
    source=Sql(
        "select coalesce(sum(c.units), 0) / 1e6 * 3.0"
        " / max(1.0, julianday(:ends) - julianday(:begins)) as value,"
        " count(distinct c.slug) as n from call_rows c"
        " join row_outcomes o on o.project = c.project and o.slug = c.slug"
        " where c.project = :project and c.role = 'crew' and o.status = 'done'"
        " and o.outcome in ('nothing to change', 'dropped', 'ended without one')"
        " and c.at >= :begins and c.at < :ends"
        " and not exists (select 1 from merged m where m.project = c.project and m.slug = c.slug)"
    ),
    window="week",
    baseline=6.5,
    baseline_of="the classing of the scout po-worse-done-no-merge, 2026-11-10",
    kind=Limit(7.8, 0),
    tier="page",
    audit=(20,),
)
