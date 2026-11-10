from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="merge-asks",
    group="attention",
    says="messages the user typed this week asking why pull requests are not merging",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message,"
        " here 'merge':"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=44,
    baseline_of="the audit of 2026-11-09, by hand: 27 to 44 per 7 days",
    kind=Limit(44, 0),
    tier="page",
    audit=(16,),
)
