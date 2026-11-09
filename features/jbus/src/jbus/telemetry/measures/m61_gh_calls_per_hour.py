from jbus.telemetry.measures import Measure, Sql, Trend

MEASURE = Measure(
    name="gh-calls-per-hour",
    group="machinery",
    says="gh calls an hour, mean of the last 24 whole hours the store holds",
    unit="calls",
    better="lower",
    source=Sql(
        "select sum(calls) * 1.0 / count(distinct hour) as value, count(distinct hour) as n"
        " from gh_hours"
        " where hour >= strftime('%Y-%m-%dT%H', :ends, '-24 hours')"
        " and hour < substr(:ends, 1, 13)",
        machine=True,
    ),
    window="day",
    baseline=10000,
    baseline_of="the audit of 2026-11-09: 94,824 calls in the log's 9 hours",
    kind=Trend(20),
    tier="page",
    audit=(36,),
)
