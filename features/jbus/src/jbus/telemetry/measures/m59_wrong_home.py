from jbus.telemetry.measures import Lacks, Measure, Zero

MEASURE = Measure(
    name="wrong-home",
    group="attention",
    says="messages the user typed this week moving a row or a home started in the wrong home",
    unit="messages",
    better="lower",
    source=Lacks(
        "messages.surface, the label po-sc-ask-labels puts on each typed message,"
        " here 'routing':"
        " messages.asks holds needs or other only"
    ),
    window="week",
    baseline=9,
    baseline_of="the audit of 2026-11-09, by hand: 5 to 9 per 7 days",
    kind=Zero(),
    tier="page",
    audit=(23,),
)
