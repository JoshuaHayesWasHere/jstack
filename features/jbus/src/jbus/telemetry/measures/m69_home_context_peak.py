from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="home-context-peak",
    group="cost",
    says=(
        "thousands of tokens of context the largest call a home sent itself in the last 72 h, no"
        " call of its subagents"
    ),
    unit="k tokens",
    better="lower",
    source=Sql(
        "select max(input + cache_write + cache_read) / 1000.0 as value, count(*) as n"
        " from call_rows where project = :project and role = 'home' and agent is null"
        " and at >= :begins and at < :ends"
    ),
    window="72h",
    baseline=630,
    baseline_of="the week's largest home call, read on 2026-11-10",
    kind=Limit(200, 1),
    tier="page",
)
