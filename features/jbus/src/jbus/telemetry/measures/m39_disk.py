from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="disk",
    group="machinery",
    says="the fuller of / and /tmp now",
    unit="%",
    better="lower",
    source=Lacks("jbus health's disk readings kept as a record each pass: df alone keeps none"),
    window="now",
    baseline=80,
    baseline_of="jbus health's limit",
    kind=Limit(80, 1),
    tier="page",
    wired="disk at 80% (jbus.health)",
)
