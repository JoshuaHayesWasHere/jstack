from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
    audit=(1,),
)
