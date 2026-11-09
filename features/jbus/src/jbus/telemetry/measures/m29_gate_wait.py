from jbus.telemetry.measures import Measure, Sql, Trend

MEASURE = Measure(
    name="gate-wait",
    group="attention",
    says="minutes a gate asked this week waited for the user's answer, mean, of those answered",
    unit="min",
    better="lower",
    source=Sql(
        "select avg((julianday(answered_at) - julianday(asked_at)) * 1440) as value,"
        " count(*) as n from questions"
        " where project = :project and closed_by = 'jbus answer' and answered_at is not null"
        " and asked_at >= :begins and asked_at < :ends"
    ),
    window="week",
    baseline=None,
    baseline_of="none yet",
    kind=Trend(20),
    tier="page",
    audit=(19,),
)
