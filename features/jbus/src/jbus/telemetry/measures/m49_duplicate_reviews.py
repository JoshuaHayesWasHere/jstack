from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="duplicate-reviews",
    group="cost",
    says="reviewers launched this week at a head a reviewer was already launched at",
    unit="launches",
    better="lower",
    source=Sql(
        "with l as (select slug, head, count(*) as k from review_launches"
        " where project = :project and launched >= :begins and launched < :ends"
        " group by slug, head)"
        " select coalesce(sum(k - 1), 0) as value, coalesce(sum(k), 0) as n from l"
    ),
    window="week",
    baseline=5,
    baseline_of="the audit of 2026-11-09: 5 per 72 h",
    kind=Zero(),
    tier="page",
    audit=(26,),
)
