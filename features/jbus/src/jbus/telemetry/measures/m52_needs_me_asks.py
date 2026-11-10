from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="needs-me-asks",
    group="attention",
    says="messages the user typed this week asking what needs them",
    unit="messages",
    better="lower",
    source=Sql(
        "select coalesce(sum(asks = 'needs'), 0) as value, count(*) as n from messages"
        " where project = :project and role = 'user' and created_by = 'user' and kind = 'text'"
        " and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=9,
    baseline_of=(
        "the rule's 9 of 483 typed in the 7 days to 2026-11-09; the audit's scouts read 27 to 29"
        " by hand, a wider class than the rule's"
    ),
    kind=Limit(10.8, 0),
    tier="page",
    audit=(19,),
)
