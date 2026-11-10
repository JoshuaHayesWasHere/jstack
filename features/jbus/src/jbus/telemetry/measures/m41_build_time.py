from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

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
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(21, 10),
    tier="page",
)
