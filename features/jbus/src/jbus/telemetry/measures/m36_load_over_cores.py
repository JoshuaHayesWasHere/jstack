from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="load-over-cores",
    group="machinery",
    says="share of today's load samples above the core count",
    unit="%",
    better="lower",
    source=Lacks("jgauge's load.tsv samples in the store"),
    window="day",
    baseline=5.4,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(6.5, 100),
    tier="page",
    audit=(40,),
)
