from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="scout-units-joined",
    group="cost",
    says="share of scout units joined to a row that merged",
    unit="%",
    better="higher",
    source=Lacks(
        "a join from a scout's session to the rows it planned: call_rows gives a scout's units,"
        " not the merged rows they led to"
    ),
    window="week",
    baseline=1.8,
    baseline_of="the audit of 2026-11-09: 1.6 M of 87.9 M scout units in 72 h",
    kind=Limit(1.4, 1),
    tier="page",
    audit=(15,),
)
