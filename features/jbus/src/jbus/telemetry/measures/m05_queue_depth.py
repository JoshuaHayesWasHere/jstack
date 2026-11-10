from jbus.telemetry.measures import Measure, Sql, Trend

MEASURE = Measure(
    name="queue-depth",
    group="flow",
    says="rows open in the queue now, of any status but done, merged or removed",
    unit="rows",
    better="lower",
    source=Sql(
        "select count(*) as value, count(*) as n from queue"
        " where project = :project and status not in ('done', 'merged', 'removed')"
    ),
    window="now",
    baseline=None,
    baseline_of="none yet: the store keeps the queue as it is now, no history of its depth",
    kind=Trend(20),
    tier="page",
)
