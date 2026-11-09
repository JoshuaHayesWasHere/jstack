from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="red-main-minutes",
    group="quality",
    says="minutes main was red in the spells that began today, each to its green",
    unit="min",
    better="lower",
    source=Sql(
        "select coalesce(sum(minutes_to_green), 0) as value, count(*) as n from main_spells"
        " where project = :project and first_fail_at >= :begins and first_fail_at < :ends"
    ),
    window="day",
    baseline=95,
    baseline_of="the audit of 2026-11-09: 285 min in 11 spells per 72 h, a day's third",
    kind=Limit(114, 0),
    tier="page",
    wired="a main-red-* row for every red tip (jbus.watch.retro)",
    audit=(25,),
)
