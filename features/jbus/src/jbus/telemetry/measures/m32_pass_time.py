from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="pass-time",
    group="machinery",
    says="seconds of jbus's passes today, mean",
    unit="s",
    better="lower",
    source=Sql(
        "select avg(seconds) as value, count(*) as n from passes"
        " where project = :project and at >= :begins and at < :ends",
        machine=True,
    ),
    window="day",
    baseline=32.5,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(39, 10),
    tier="page",
    wired="pass-time, p90 over 60 s in the last hour (jbus.kpis)",
    audit=(35,),
)
