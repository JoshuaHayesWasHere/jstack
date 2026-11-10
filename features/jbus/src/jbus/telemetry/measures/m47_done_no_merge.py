from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="done-no-merge",
    group="cost",
    says=(
        "crew units in the last 72 h on rows that ended done with no merge and bought none: nothing to"
        " change, dropped, or ended with no outcome named (`row_outcomes`), in millions"
    ),
    unit="M units per 72 h",
    better="lower",
    source=Sql(
        "select coalesce(sum(c.units), 0) / 1e6 as value,"
        " count(distinct c.slug) as n from call_rows c"
        " join row_outcomes o on o.project = c.project and o.slug = c.slug"
        " where c.project = :project and c.role = 'crew' and o.status = 'done'"
        " and o.outcome in ('nothing to change', 'dropped', 'ended without one')"
        " and c.at >= :begins and c.at < :ends"
        " and not exists (select 1 from merged m where m.project = c.project and m.slug = c.slug)"
    ),
    window="72h",
    baseline=6.5,
    baseline_of="the classing of the scout po-worse-done-no-merge, 2026-11-10",
    kind=Limit(7.8, 0),
    tier="page",
    audit=(20,),
)
