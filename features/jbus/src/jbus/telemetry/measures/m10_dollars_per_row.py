from datetime import date

from jbus.telemetry.measures import Measure, Over, Sql, Week
from jbus.telemetry.views.row_spend import CLASSES

WEEK = "week in (date(:begins), date(:begins, '+1 day'))"
"""The week the window begins, a Sunday in the user's zone, whose start `:begins` holds in UTC."""

PARTS = (
    f"WITH {CLASSES}, "
    "merged AS (SELECT DISTINCT project, slug FROM lead_times "
    f"WHERE project = :project AND {WEEK}), "
    "per_row AS (SELECT count(DISTINCT slug) AS rows FROM row_spend "
    f"WHERE project = :project AND {WEEK}), "
    "roles AS (SELECT coalesce(role, 'other') AS role, "
    "coalesce(sum(dollars), 0) / (SELECT rows FROM per_row) AS value "
    f"FROM row_spend WHERE project = :project AND {WEEK} GROUP BY 1), "
    "shares AS (SELECT k.class, sum(k.dollars) / (SELECT sum(j.dollars) FROM crew_classes j "
    "JOIN merged m ON m.project = j.project AND m.slug = j.slug) AS share "
    "FROM crew_classes k JOIN merged m ON m.project = k.project AND m.slug = k.slug "
    "GROUP BY k.class) "
    "SELECT role AS label, value, NULL AS line FROM roles "
    "UNION ALL SELECT 'crew: ' || s.class, r.value * s.share, NULL FROM shares s "
    "JOIN roles r ON r.role = 'crew' WHERE s.share IS NOT NULL "
    "ORDER BY label"
)
"""Each role's dollars a row, crew, reviewer, home and scout, which sum to the value, then the
crew's split by what woke each run (`row_spend.CLASSES`): the share of the class in the crew
dollars T3 Code counted for the week's merged rows (`spend_rows`), times the crew's dollars a
row, so the classes sum to the crew's part."""

MEASURE = Measure(
    name="dollars-per-row",
    group="cost",
    says=(
        "dollars per row merged this week, at API list prices; each role is shown, and the "
        "crew's by what woke each run"
    ),
    unit="$",
    better="lower",
    source=Sql(
        "select dollars_per_row as value, rows as n from weekly_row_spend"
        " where project = :project and week in (date(:begins), date(:begins, '+1 day'))",
        each=PARTS,
    ),
    window="week",
    baseline=Week(date(2026, 11, 1)),
    baseline_of="the same query over the week of 2026-11-01",
    kind=Over(20, 5),
    tier="page",
    each_unit="$ a row merged this week",
)
