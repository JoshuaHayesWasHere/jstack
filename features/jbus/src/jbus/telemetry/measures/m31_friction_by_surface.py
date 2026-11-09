from jbus.telemetry.measures import Lacks, Measure, Trend

MEASURE = Measure(
    name="friction-by-surface",
    group="attention",
    says="friction messages the user typed this week: sidebar, merge line, exact words, routing",
    unit="messages",
    better="lower",
    source=Lacks(
        "a label on each typed message by the surface it is friction with:"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=210,
    baseline_of="the audit of 2026-11-09, by hand: 210 to 256 per 7 days",
    kind=Trend(20),
    tier="page",
    audit=(3, 10, 16, 23),
)
