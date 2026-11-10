from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="closed-unmerged",
    group="cost",
    says="pull requests closed this week with no merge, per 72 h",
    unit="per 72 h",
    better="lower",
    source=Sql(
        "select count(*) * 3.0 / max(1.0, julianday(:ends) - julianday(:begins)) as value,"
        " count(*) as n from ci_prs where project = :project and merged is null"
        " and closed >= :begins and closed < :ends"
    ),
    window="week",
    baseline=9,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(10.8, 0),
    tier="page",
    audit=(24,),
)
