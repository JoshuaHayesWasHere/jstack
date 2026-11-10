from jbus.telemetry.measures import Lacks, Measure, Trend

MEASURE = Measure(
    name="fix-share",
    group="quality",
    says="share of today's commits on main that are fixes",
    unit="%",
    better="lower",
    source=Lacks(
        "a record of main's commits by day and kind, fix or not: the store reads no git log"
    ),
    window="day",
    baseline=49,
    baseline_of="the audit of 2026-11-09: 118 of 240 commits in 72 h",
    kind=Trend(20),
    tier="page",
    audit=(30,),
)
