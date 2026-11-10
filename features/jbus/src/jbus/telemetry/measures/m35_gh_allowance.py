from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="gh-allowance",
    group="machinery",
    says="the lowest core allowance of gh calls left in the last hour",
    unit="calls",
    better="higher",
    source=Lacks(
        "an hourly roll-up of gh-calls.jsonl into the store before the log rotates at 16 MB"
    ),
    window="hour",
    baseline=None,
    baseline_of="none yet: the audit counted about 10,000 calls an hour, not the allowance left",
    kind=Limit(500, 1),
    tier="wake",
    audit=(36,),
)
