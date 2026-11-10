from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="failed-launches",
    group="machinery",
    says="share of the last hour's first launches that failed",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(from_status = 'launched' and to_status = 'failed')"
        " / nullif(sum(from_status = 'queued' and to_status = 'launched'), 0) as value,"
        " coalesce(sum(from_status = 'queued' and to_status = 'launched'), 0) as n"
        " from transitions where project = :project and at >= :begins and at < :ends"
    ),
    window="hour",
    baseline=0,
    baseline_of="0 since the fix of 2026-11-09",
    kind=Limit(20, 5),
    tier="wake",
    audit=(27,),
)
