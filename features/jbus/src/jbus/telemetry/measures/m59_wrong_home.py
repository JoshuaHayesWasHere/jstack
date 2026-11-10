from jbus.telemetry.measures import Lacks, Measure, Zero

MEASURE = Measure(
    name="wrong-home",
    group="attention",
    says="messages the user typed this week moving a row or a home started in the wrong home",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule that tells a message about routing: asks.surface agreed with the audit's"
        " hand label on 1 of 2 (50%) on a held-out 100 of the audit's typed messages"
        " (2026-11-02 to 11-09), under the 80% to show it"
    ),
    window="week",
    baseline=9,
    baseline_of="the audit of 2026-11-09, by hand: 5 to 9 per 7 days",
    kind=Zero(),
    tier="page",
    audit=(23,),
)
