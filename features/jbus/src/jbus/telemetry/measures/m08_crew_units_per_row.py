from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="crew-units-per-row",
    group="cost",
    says="crew units per row merged this week, in millions",
    unit="M units",
    better="lower",
    source=Sql(
        "select sum(units) / 1e6 / nullif(count(distinct slug), 0) as value,"
        " count(distinct slug) as n from row_spend"
        " where project = :project and role = 'crew'"
        " and merged_at >= :begins and merged_at < :ends"
    ),
    window="week",
    baseline=3.86,
    baseline_of="last week's row_spend, the week of 2026-11-01",
    kind=Limit(4.63, 5),
    tier="page",
    audit=(1,),
)
