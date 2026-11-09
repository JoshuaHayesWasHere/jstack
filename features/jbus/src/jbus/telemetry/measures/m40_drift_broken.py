from jbus.telemetry.measures import Limit, Measure, Sql

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
    baseline=3,
    baseline_of="drift last week",
    kind=Limit(3.6, 1),
    tier="page",
)
