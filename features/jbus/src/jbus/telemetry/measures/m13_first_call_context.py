from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="first-call-context",
    group="cost",
    says="k tokens of context of the first call of a crew session begun this week, mean",
    unit="k tokens",
    better="lower",
    source=Sql(
        "with f as (select session, min(at) as at from call_rows"
        " where project = :project and role = 'crew' group by session"
        " having min(at) >= :begins and min(at) < :ends)"
        " select avg(c.input + c.cache_write + c.cache_read) / 1000.0 as value, count(*) as n"
        " from f join calls c on c.session = f.session and c.at = f.at"
    ),
    window="week",
    baseline=47.9,
    baseline_of="the audit of 2026-11-09, crew and reviewer",
    kind=Limit(57.5, 5),
    tier="page",
    audit=(18,),
)
