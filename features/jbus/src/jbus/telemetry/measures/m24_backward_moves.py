from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="backward-moves",
    group="quality",
    says=(
        "status moves out of merged or done in the last 72 h, which should be none,"
        " leaving out a scout's done row handed to its crewmate and a merged row whose revert"
        " merged"
    ),
    unit="moves",
    better="lower",
    source=Sql(
        "select count(*) as value, count(*) as n from transitions"
        " where project = :project and from_status in ('merged', 'done') and handed = 0"
        " and reverted = 0"
        " and at >= :begins and at < :ends"
    ),
    window="72h",
    baseline=17,
    baseline_of="the audit of 2026-11-09: 17 per 72 h",
    kind=Zero(),
    tier="page",
    audit=(31,),
)
