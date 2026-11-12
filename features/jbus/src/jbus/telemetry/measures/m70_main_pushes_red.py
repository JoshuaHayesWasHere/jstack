from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week

MEASURE = Measure(
    name="main-pushes-red",
    group="quality",
    says=(
        "share of main's push checks that ended red in the last 72 h; it counts pushes, not "
        "spells, and a red main holds no merge, so one long spell counts once a push: "
        "red-spells-per-merge counts each spell once over the same 72 h"
    ),
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * sum(state = 'red') / nullif(count(*), 0) as value, count(*) as n"
        " from main_checks where project = :project and state in ('red', 'green')"
        " and completed >= :begins and completed < :ends",
        note=(
            "with counted as (select (select count(*) from main_checks"
            " where project = :project and state = 'red' and completed >= :begins"
            " and completed < :ends) as pushes, (select count(*) from main_spells"
            " where project = :project and first_fail_at >= :begins and first_fail_at < :ends)"
            " as spells) select pushes || ' red pushes in ' || spells || ' spells' from counted"
            " where pushes > 0"
        ),
    ),
    window="72h",
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 20),
    tier="page",
)
