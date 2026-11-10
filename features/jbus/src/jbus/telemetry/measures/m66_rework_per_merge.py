from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="rework-per-merge",
    group="flow",
    says="jmerge waits that send a pull request back for more work (content changed, dropped,"
    " conflicts, proved stale, checked stale) per pull request merged today",
    unit="waits",
    better="lower",
    source=Sql(
        "with landed as (select count(*) as n from merged where project = :project"
        " and merged_at >= :begins and merged_at < :ends)"
        " select (select count(*) from merges where project = :project and verb = 'wait'"
        " and label in ('content-changed', 'dropped', 'conflicts', 'proved-stale',"
        " 'checked-stale') and at >= :begins and at < :ends) * 1.0 / nullif(n, 0) as value, n"
        " from landed"
    ),
    window="day",
    baseline=2.1,
    baseline_of="po-retro-2: 209 rework waits over 99 merges, 2026-11-09",
    kind=Limit(2.52, 10),
    tier="page",
)
