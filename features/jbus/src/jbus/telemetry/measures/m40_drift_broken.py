from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

MEASURE = Measure(
    name="drift-broken",
    group="machinery",
    says="drift probes broken at their latest run",
    unit="probes",
    better="lower",
    source=Sql(
        "select sum(status = 'broken') as value, count(*) as n from drift"
        " where project = :project and at = (select max(at) from drift"
        " where project = :project and at <= :ends)",
        machine=True,
    ),
    window="now",
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 1),
    tier="page",
)
