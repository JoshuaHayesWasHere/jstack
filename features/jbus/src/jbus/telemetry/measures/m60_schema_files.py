from jbus.telemetry.measures import Lacks, Measure, Trend

MEASURE = Measure(
    name="schema-files",
    group="machinery",
    says="state files jstack writes that declare no schema",
    unit="files",
    better="lower",
    source=Lacks(
        "a record of each state file jstack writes and whether it declares a schema: the store"
        " reads no file of state, and the audit counted them in the source by hand"
    ),
    window="now",
    baseline=150,
    baseline_of="the audit of 2026-11-09: 87 to 150 files, 0 with a declared schema",
    kind=Trend(20),
    tier="page",
    audit=(32,),
)
