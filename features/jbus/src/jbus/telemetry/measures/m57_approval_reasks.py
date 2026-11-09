from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="approval-reasks",
    group="attention",
    says="approvals the user typed again this week because the words did not bind",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message,"
        " here 'exact words':"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=24,
    baseline_of="the audit of 2026-11-09, by hand: 12 to 24 per 7 days",
    kind=Limit(24, 0),
    tier="page",
    audit=(21,),
)
