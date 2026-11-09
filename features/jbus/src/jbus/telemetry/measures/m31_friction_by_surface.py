from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="friction-by-surface",
    group="attention",
    says="friction messages the user typed this week, of every surface",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message by the surface"
        " it is friction with: messages.asks holds needs or other only"
    ),
    window="week",
    baseline=256,
    baseline_of="the audit of 2026-11-09, by hand: 210 to 256 per 7 days",
    kind=Limit(256, 0),
    tier="page",
    audit=(3,),
)
