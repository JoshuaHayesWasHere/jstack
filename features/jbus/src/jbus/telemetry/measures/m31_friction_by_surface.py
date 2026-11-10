from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="friction-by-surface",
    group="attention",
    says="friction messages the user typed this week, of every surface",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule whose other agrees with the audit's hand label: asks.surface and scout 2 agreed"
        " on other or not on 73 of a held-out 100 of the audit's typed messages"
        " (2026-11-02 to 11-09), under the 80% to show it"
    ),
    window="week",
    baseline=256,
    baseline_of="the audit of 2026-11-09, by hand: 210 to 256 per 7 days",
    kind=Limit(256, 0),
    tier="page",
    audit=(3,),
)
