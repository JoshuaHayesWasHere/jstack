from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="sidebar-friction",
    group="attention",
    says="messages the user typed this week the sidebar did not answer: is it moving, needs me",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message,"
        " here 'sidebar':"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=75,
    baseline_of="the audit of 2026-11-09, by hand: 46 to 75 per 7 days",
    kind=Limit(75, 0),
    tier="page",
    audit=(10,),
)
