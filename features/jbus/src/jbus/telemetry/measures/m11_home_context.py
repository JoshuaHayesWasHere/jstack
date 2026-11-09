from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="home-context",
    group="cost",
    says="thousands of tokens of context a home call sends, mean, this week",
    unit="k tokens",
    better="lower",
    source=Sql(
        "select avg(input + cache_write + cache_read) / 1000.0 as value, count(*) as n"
        " from call_rows where project = :project and role = 'home'"
        " and at >= :begins and at < :ends"
    ),
    window="week",
    baseline=182,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(218.4, 20),
    tier="page",
    audit=(9,),
)
