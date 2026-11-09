from jbus.telemetry.measures import Lacks, Measure, Trend

MEASURE = Measure(
    name="slot-wait",
    group="machinery",
    says="hours waited today for a test slot",
    unit="h",
    better="lower",
    source=Lacks("jgauge's slots.jsonl takes in the store"),
    window="day",
    baseline=0.31,
    baseline_of="slots.jsonl on 2026-11-07",
    kind=Trend(20),
    tier="page",
)
