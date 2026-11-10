from jbus.telemetry.measures import SESSION_HOURS, SPANS, Limit, Measure, Sql

MEASURE = Measure(
    name="gh-calls-per-session-hour",
    group="machinery",
    says="GitHub core calls that cost (a 304 does not) per live session-hour today, every caller"
    " on the user's token; 5,000 an hour over it is the sessions the token carries. Under 20"
    " session-hours it is no reading: the idle floor (gh-idle-calls-per-hour) is most of it",
    unit="calls",
    better="lower",
    source=Sql(
        f"{SPANS} select (select sum(calls - not_modified) from gh_hours where resource = 'core'"
        " and hour >= substr(:begins, 1, 13) and hour || ':00:00.000000Z' < :ends)"
        f" / {SESSION_HOURS} as value, {SESSION_HOURS} as n",
        machine=True,
    ),
    window="day",
    baseline=171,
    baseline_of="po-retro-3: 23,910 costed core calls over 140.1 session-hours, 2026-11-09",
    kind=Limit(205, 20),
    tier="page",
)
