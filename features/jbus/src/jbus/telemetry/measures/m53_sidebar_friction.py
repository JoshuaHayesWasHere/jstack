from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="sidebar-friction",
    group="attention",
    says="messages the user typed this week the sidebar did not answer: is it moving, needs me",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule that tells a message about the sidebar: asks.surface agreed with the audit's"
        " hand label on 9 of 13 (69%) on a held-out 100 of the audit's typed messages"
        " (2026-11-02 to 11-09), under the 80% to show it"
    ),
    window="week",
    baseline=75,
    baseline_of="the audit of 2026-11-09, by hand: 46 to 75 per 7 days",
    kind=Limit(75, 0),
    tier="page",
    audit=(10,),
)
