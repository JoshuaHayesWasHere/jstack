from jbus.telemetry.measures import Measure, Sql, Trend

MEASURE = Measure(
    name="crew-first-load",
    group="cost",
    says="KB a crew reads of jstack's skill and playbook before its work, largest today",
    unit="KB",
    better="lower",
    source=Sql(
        "select max(bytes) / 1000.0 as value, count(*) as n from first_loads"
        " where project = :project and at >= :begins and at < :ends",
        machine=True,
    ),
    window="day",
    baseline=16.3,
    baseline_of="first_loads on 2026-11-03",
    kind=Trend(20),
    tier="page",
)
