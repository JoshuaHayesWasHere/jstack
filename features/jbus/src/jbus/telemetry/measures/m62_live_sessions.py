from jbus.telemetry.measures import SPANS, Measure, Sql, Trend

MEASURE = Measure(
    name="live-sessions",
    group="machinery",
    says="the most sessions live at once today, a session a thread between its first and last"
    " model call, on every project",
    unit="sessions",
    better="higher",
    source=Sql(
        f"{SPANS} select max((select count(*) from spans b"
        " where b.first <= a.first and b.last >= a.first)) as value, count(*) as n from spans a",
        machine=True,
    ),
    window="day",
    baseline=48,
    baseline_of="po-retro-3: the push of 2026-11-09, 20:00 to 02:00 UTC, at its peak",
    kind=Trend(50),
    tier="page",
)
