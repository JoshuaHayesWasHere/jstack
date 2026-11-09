from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="disk",
    group="machinery",
    says="the fullest mount jbus writes to today, of space or inodes, highest",
    unit="%",
    better="lower",
    source=Sql(
        "select max(value) as value, count(*) as n from health_readings"
        " where project = :project and at >= :begins and at < :ends"
        " and (reading like 'disk %' or reading like 'inodes %')",
        machine=True,
    ),
    window="day",
    baseline=80,
    baseline_of="jbus health's limit",
    kind=Limit(80, 1),
    tier="page",
    wired="health, disk or inodes at 80% (jbus.health)",
)
