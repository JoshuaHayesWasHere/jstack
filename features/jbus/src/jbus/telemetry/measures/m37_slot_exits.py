from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="slot-exits",
    group="machinery",
    says="share of today's short test-slot commands that exit nonzero",
    unit="%",
    better="lower",
    source=Lacks("jgauge's slots.jsonl releases in the store"),
    window="day",
    baseline=13.6,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(16.3, 20),
    tier="page",
    audit=(39,),
)
