from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="capped-any-minutes",
    group="machinery",
    says=(
        "minutes with an account capped, while launches ran on the others, a day of this week so"
        " far; the capped minutes KPI counts every account capped"
    ),
    unit="min a day",
    better="lower",
    source=Sql(
        "select coalesce(sum(minutes), 0) / max(1.0, julianday(:ends) - julianday(:begins))"
        " as value, coalesce(sum(reads), 0) as n"
        " from weekly_capped_any where project = :project and week = date(:begins, 'weekday 0')",
        machine=True,
    ),
    window="week",
    baseline=5585 / 7,
    baseline_of="weekly_capped_any, the week of 2026-11-01: 5,585, 798 a day",
    kind=Limit(5585 / 7, 1),
    tier="page",
)
