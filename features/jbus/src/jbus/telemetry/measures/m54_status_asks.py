from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="status-asks",
    group="attention",
    says="messages the user typed this week asking a home for status",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message,"
        " here 'status':"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=76,
    baseline_of="the audit of 2026-11-09, by hand: 34 to 76 per 7 days",
    kind=Limit(91.2, 0),
    tier="page",
    audit=(13,),
)
