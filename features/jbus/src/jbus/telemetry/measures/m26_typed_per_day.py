from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="typed-per-day",
    group="attention",
    says="messages the user typed today",
    unit="messages",
    better="lower",
    source=Sql(
        "select coalesce(sum(kind = 'text'), 0) as value, count(*) as n from messages"
        " where project = :project and role = 'user' and created_by = 'user'"
        " and at >= :begins and at < :ends"
    ),
    window="day",
    baseline=68,
    baseline_of="the mean of the 7 days to 2026-11-09",
    kind=Limit(81.6, 0),
    tier="page",
)
