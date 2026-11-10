from jbus.telemetry.measures import SESSION_HOURS, SPANS, Limit, Measure, Sql

MEASURE = Measure(
    name="merges-per-session-hour",
    group="flow",
    says="pull requests merged today on every project per live session-hour",
    unit="merges",
    better="higher",
    source=Sql(
        f"{SPANS}, landed as (select count(*) as n from merged"
        " where merged_at >= :begins and merged_at < :ends)"
        f" select n / {SESSION_HOURS} as value, n from landed",
        machine=True,
    ),
    window="day",
    baseline=0.71,
    baseline_of="po-retro-3: 100 merges over 140.1 session-hours, 2026-11-09",
    kind=Limit(0.57, 10),
    tier="page",
)
