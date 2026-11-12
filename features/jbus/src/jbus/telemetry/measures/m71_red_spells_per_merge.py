from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

MEASURE = Measure(
    name="red-spells-per-merge",
    group="quality",
    says=(
        "red spells of main's push checks opened in the last 72 h, per merge in the same 72 h; "
        "it counts each spell once however many pushes it held, where main-pushes-red counts "
        "each red push"
    ),
    unit="spells a merge",
    better="lower",
    source=Sql(
        "with landed as (select count(*) as n from merged where project = :project"
        " and merged_at >= :begins and merged_at < :ends)"
        " select (select count(*) from main_spells where project = :project"
        " and first_fail_at >= :begins and first_fail_at < :ends) * 1.0 / nullif(n, 0)"
        " as value, n from landed",
        note=(
            "with counted as (select (select count(*) from main_spells"
            " where project = :project and first_fail_at >= :begins and first_fail_at < :ends)"
            " as spells, (select count(*) from merged where project = :project"
            " and merged_at >= :begins and merged_at < :ends) as merges,"
            " (select count(*) from main_checks where project = :project and state = 'red'"
            " and completed >= :begins and completed < :ends) as pushes)"
            " select spells || ' spells over ' || merges || ' merges; ' || pushes"
            " || ' red pushes' from counted where merges > 0 or spells > 0"
        ),
    ),
    window="72h",
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 20),
    tier="page",
)
