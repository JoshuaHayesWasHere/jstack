from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="backward-moves",
    group="quality",
    says="status moves out of merged or done this week, which should be none",
    unit="moves",
    better="lower",
    source=Sql(
        "select count(*) as value, count(*) as n from transitions"
        " where project = :project and from_status in ('merged', 'done')"
        " and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=17,
    baseline_of="the audit of 2026-11-09: 17 per 72 h",
    kind=Zero(),
    tier="page",
    audit=(31,),
)
