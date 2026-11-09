from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="capped-reads",
    group="machinery",
    says="share of today's limit reads with an account capped",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(capped > 0) / nullif(count(*), 0) as value, count(*) as n"
        " from capped_reads where project = :project and at >= :begins and at < :ends",
        machine=True,
    ),
    window="day",
    baseline=100,
    baseline_of="capped_reads on 2026-11-05 to 07",
    kind=Limit(100, 10),
    tier="page",
    wired="capped, every instance capped over 30 min a day (jbus.kpis)",
)
