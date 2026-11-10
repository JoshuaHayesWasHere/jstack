from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="approval-reasks",
    group="attention",
    says=(
        "approvals the user typed in T3, re-asks of words that did not bind among them, a day of"
        " this week so far"
    ),
    unit="messages a day",
    better="lower",
    source=Sql(
        "select coalesce(sum(surface = 'approval'), 0)"
        " / max(1.0, julianday(:ends) - julianday(:begins)) as value, count(surface) as n"
        " from messages where project = :project and role = 'user' and created_by = 'user'"
        " and kind = 'text' and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=143 / 7,
    baseline_of=(
        "asks.surface over the 7 days to 2026-11-09: 143, 20.4 a day; by hand, 12 to 24 re-asks"
    ),
    kind=Limit(171.6 / 7, 0),
    tier="page",
    audit=(21,),
)
