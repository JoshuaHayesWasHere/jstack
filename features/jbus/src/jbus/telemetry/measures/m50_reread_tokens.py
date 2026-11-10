from jbus.telemetry.measures import Lacks, Measure, Trend

MEASURE = Measure(
    name="reread-tokens",
    group="cost",
    says="tokens sessions spent this week reading again a file they had read, in millions",
    unit="M tokens",
    better="lower",
    source=Lacks(
        "a record of each read a session makes, by file: calls give a call's tokens, not what it"
        " read, and the audit's count came from the scouts' scripts over the transcripts"
    ),
    window="week",
    baseline=0.42,
    baseline_of="the audit of 2026-11-09: 0.42 M per 72 h, 0.008% of tokens",
    kind=Trend(50),
    tier="page",
    audit=(28,),
)
