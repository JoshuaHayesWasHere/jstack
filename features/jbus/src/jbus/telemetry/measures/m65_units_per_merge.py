from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="units-per-merge",
    group="cost",
    says="every unit spent today, any role on any project, per pull request merged today,"
    " in millions",
    unit="M units",
    better="lower",
    source=Sql(
        "with landed as (select count(*) as n from merged"
        " where merged_at >= :begins and merged_at < :ends)"
        " select (select sum(units) from call_rows"
        " where day >= date(:begins, '-1 day') and day <= date(:ends, '+1 day')"
        " and at >= :begins and at < :ends) / 1e6 / nullif(n, 0) as value, n from landed",
        machine=True,
    ),
    window="day",
    baseline=3.76,
    baseline_of="po-retro-3: the push of 2026-11-09, call_rows over its 99 merges",
    kind=Limit(4.51, 10),
    tier="page",
)
