from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="lost-asks",
    group="attention",
    says="asks lost this week: a typed message with no act citing it and no reply in time",
    unit="asks",
    better="lower",
    source=Sql(
        "select lost as value, typed as n from weekly_lost_asks"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))"
    ),
    window="week",
    baseline=0,
    baseline_of="the audit of 2026-11-09: 0 of 542",
    kind=Zero(),
    tier="page",
    wired="lost-asks, on 1 a day (jbus.kpis)",
)
