from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="held-ready-pr",
    group="flow",
    says="hours the longest-held ready pull request has waited on a held row",
    unit="h",
    better="lower",
    source=Sql(
        "select coalesce(max(held), 0) / 3600.0 as value, count(*) as n from held_now"
        " where project = :project"
    ),
    window="now",
    baseline=19.9,
    baseline_of="the audit of 2026-11-09: 19.9 to 25.9 h on row-held per 72 h, all pull requests",
    kind=Limit(2, 0),
    tier="wake",
    audit=(8,),
)
