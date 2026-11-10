from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="merge-asks",
    group="attention",
    says=(
        "messages the user typed naming a pull request or CI, asks and work alike, a day of this"
        " week so far"
    ),
    unit="messages a day",
    better="lower",
    source=Sql(
        "select coalesce(sum(surface = 'merge'), 0)"
        " / max(1.0, julianday(:ends) - julianday(:begins)) as value, count(surface) as n"
        " from messages where project = :project and role = 'user' and created_by = 'user'"
        " and kind = 'text' and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=40 / 7,
    baseline_of=(
        "asks.surface over the 7 days to 2026-11-09: 40, 5.7 a day; by hand, 27 to 44 per 7 days"
    ),
    kind=Limit(48 / 7, 0),
    tier="page",
    audit=(16,),
)
