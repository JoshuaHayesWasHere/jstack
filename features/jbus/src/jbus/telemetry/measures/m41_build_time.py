from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="build-time",
    group="machinery",
    says="seconds of the telemetry store's builds today, mean",
    unit="s",
    better="lower",
    source=Sql(
        "select avg(ms) / 1000.0 as value, count(*) as n from builds"
        " where at >= :begins and at < :ends",
        machine=True,
    ),
    window="day",
    baseline=0.33,
    baseline_of="builds last week",
    kind=Limit(0.4, 10),
    tier="page",
)
