from jbus.telemetry.measures import Lacks, Limit, Measure

MEASURE = Measure(
    name="held-ready-pr",
    group="flow",
    says="hours the longest-held ready pull request has waited on a held row",
    unit="h",
    better="lower",
    source=Lacks(
        "a span per ready pull request a held row holds, from its first row-held wait to its"
        " merge: merge_waits gives each wait verdict's seconds by blocker, not one pull"
        " request's hold"
    ),
    window="now",
    baseline=19.9,
    baseline_of="the audit of 2026-11-09: 19.9 to 25.9 h on row-held per 72 h, all pull requests",
    kind=Limit(2, 1),
    tier="wake",
    audit=(8,),
)
