from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="reply-corrections",
    group="attention",
    says="messages the user typed this week correcting a home's reply for wording or accuracy",
    unit="messages",
    better="lower",
    source=Lacks(
        "a rule that tells a correction from a request: no pattern of the words does,"
        " so asks.surface has no label for one"
    ),
    window="week",
    baseline=18,
    baseline_of="the audit of 2026-11-09, by hand: 18 per 7 days",
    kind=Limit(21.6, 0),
    tier="page",
    audit=(17,),
)
