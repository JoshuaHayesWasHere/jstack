from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="gh-allowance",
    group="machinery",
    says="the lowest allowance of gh calls left in the last hour, core or graphql, whichever is"
    " nearer its wall",
    unit="calls",
    better="higher",
    source=Sql(
        "select min(least) as value, sum(calls) as n from gh_hours"
        " where resource in ('core', 'graphql')"
        " and hour >= substr(:begins, 1, 13) and hour <= substr(:ends, 1, 13)",
        machine=True,
    ),
    window="hour",
    baseline=1000,
    baseline_of="jsettings.budget.FLOOR, the allowance jbus budget holds callers at",
    kind=Limit(1000, 1),
    tier="page",
    wired="jbus budget, which holds every caller at 1,000 calls left (jsettings.budget.FLOOR)",
)
