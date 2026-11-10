"""`again` and `head` are the view's (`jbus.telemetry.views.review_launches`): a launch whose
head jbus did not record is in no count, and the note says how many of the last 72 h's launches those
are, so a launcher that records no head shows."""

from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="duplicate-reviews",
    group="cost",
    says=(
        "reviewers launched in the last 72 h at a head a reviewer of the same seat was already launched"
        " at, of the launches whose head jbus recorded"
    ),
    unit="launches",
    better="lower",
    source=Sql(
        "select coalesce(sum(again > 0), 0) as value, count(*) as n from review_launches"
        " where project = :project and launched >= :begins and launched < :ends"
        " and head is not null",
        note=(
            "select count(*) filter (where head is null) || ' of ' || count(*)"
            " || ' launches have no recorded head' from review_launches"
            " where project = :project and launched >= :begins and launched < :ends"
            " having count(*) > 0"
        ),
    ),
    window="72h",
    baseline=5,
    baseline_of="the audit of 2026-11-09: 5 per 72 h",
    kind=Zero(),
    tier="page",
    audit=(26,),
)
