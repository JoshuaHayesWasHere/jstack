from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="status-asks",
    group="attention",
    says="messages the user typed this week asking a home for status",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule that tells a message about status: asks.surface agreed with the audit's"
        " hand label on 3 of 11 (27%) on a held-out 100 of the audit's typed messages"
        " (2026-11-02 to 11-09), under the 80% to show it"
    ),
    window="week",
    baseline=76,
    baseline_of="the audit of 2026-11-09, by hand: 34 to 76 per 7 days",
    kind=Limit(91.2, 0),
    tier="page",
    audit=(13,),
)
