from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="visual-misses",
    group="attention",
    says="messages the user typed this week correcting a visual or a report that missed the ask",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule that tells a correction from a request: no pattern of the words does,"
        " so asks.surface has no label for one"
    ),
    window="week",
    baseline=13,
    baseline_of="the audit of 2026-11-09, by hand: 8 to 13 per 7 days",
    kind=Limit(15.6, 0),
    tier="page",
    audit=(22,),
)
