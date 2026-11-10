from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="merged-per-day",
    group="flow",
    says="rows merged a day, over the days of this week so far",
    unit="rows a day",
    better="higher",
    source=Sql(
        "select count(*) / max(1.0, julianday(:ends) - julianday(:begins)) as value, count(*) as n"
        " from merged where project = :project and merged_at >= :begins and merged_at < :ends"
    ),
    window="week",
    baseline=71,
    baseline_of="the mean of the 7 days to 2026-11-09",
    kind=Limit(56.8, 20),
    tier="page",
)
