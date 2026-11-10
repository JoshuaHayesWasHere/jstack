from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="gh-idle-calls-per-hour",
    group="machinery",
    says="GitHub core calls that cost (a 304 does not) an hour, mean of today's whole hours with"
    " under half a live session-hour in them, a thread live in an hour from its first to its"
    " last model call in that hour: the floor the machine spends with no one at work",
    unit="calls",
    better="lower",
    source=Sql(
        "with live as (select substr(c.at, 1, 13) as hour,"
        " (julianday(max(c.at)) - julianday(min(c.at))) * 24 as hours"
        " from calls c left join sessions s on s.provider = c.provider and s.session = c.session"
        " where c.day >= date(:begins, '-1 day') and c.day <= date(:ends, '+1 day')"
        " and c.at >= :begins and c.at < :ends"
        " group by coalesce(s.thread, c.provider || ':' || c.session), 1),"
        " hours as (select hour, sum(calls - not_modified) as cost from gh_hours"
        " where resource = 'core' and hour >= substr(:begins, 1, 13)"
        " and hour < substr(:ends, 1, 13) group by hour)"
        " select avg(cost) as value, count(*) as n from hours h"
        " where coalesce((select sum(hours) from live where live.hour = h.hour), 0) < 0.5",
        machine=True,
    ),
    window="day",
    baseline=2130,
    baseline_of="po-worse-gh-calls: hours 08 to 11 UTC of 2026-11-10, 0 to 3 threads live,"
    " before #1584",
    kind=Limit(300),
    tier="page",
)
