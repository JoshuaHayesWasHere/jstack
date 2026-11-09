from jbus.telemetry.measures import Measure, Sql, Trend

MEASURE = Measure(
    name="reviewer-units-per-row",
    group="cost",
    says="reviewer units per row merged this week, in millions",
    unit="M units",
    better="lower",
    source=Sql(
        "select sum(units) / 1e6 / nullif(count(distinct slug), 0) as value,"
        " count(distinct slug) as n from row_spend"
        " where project = :project and role = 'reviewer'"
        " and merged_at >= :begins and merged_at < :ends"
    ),
    window="week",
    baseline=None,
    baseline_of="none yet",
    kind=Trend(20),
    tier="page",
    audit=(13,),
)
