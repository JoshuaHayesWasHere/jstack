from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="merge-asks",
    group="attention",
    says="messages the user typed this week naming a pull request or CI, asks and work alike",
    unit="messages",
    better="lower",
    source=Sql(
        "select coalesce(sum(surface = 'merge'), 0) as value, count(surface) as n from messages"
        " where project = :project and role = 'user' and created_by = 'user' and kind = 'text'"
        " and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=40,
    baseline_of="asks.surface over the 7 days to 2026-11-09: 40; by hand, 27 to 44 per 7 days",
    kind=Limit(48, 0),
    tier="page",
    audit=(16,),
)
