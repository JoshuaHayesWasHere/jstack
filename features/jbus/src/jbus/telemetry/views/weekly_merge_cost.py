"""Each week's cost per successful merge (`merge_cost`): `merges`, the successful merges whose 7
days end in the week, and `waiting`, its merges whose 7 days are not over yet, which are not
successful yet and whose calls all-in counts; the successful merges' own dollars and units, their
sum, mean and median; and the week's all-in dollars over them (`all_in_per_merge`), none for a
week with no successful merge.

All-in is the dollars of every priced call of the week, a call of no merged row too: a home's, a
scout's, a crew's whose row never merged and a redone row's, though not a call of a thread of no
role (`other`). A call counts in the week its day plus `redo_rows.REDO_DAYS` falls in, so that
its week is the one a merge made the same day counts in: a week's merges and its calls are both
those made in the week before it. A merge with no call recorded counts as none spent. The median
is the mean of the two middle values for an even count, as `statistics.median`."""

from jbus.roles import OTHER
from jbus.telemetry.schema import WEEK
from jbus.telemetry.views.redo_rows import REDO_DAYS

SQL = (
    "WITH own AS (SELECT r.week, coalesce(sum(m.dollars), 0) AS dollars, "
    "coalesce(sum(m.units), 0) AS units FROM redo_rows r LEFT JOIN merge_cost m "
    "ON m.project = r.project AND m.slug = r.slug WHERE r.judged AND r.redone_by IS NULL "
    "GROUP BY r.project, r.slug), "
    "ranked AS (SELECT week, dollars, units, count(*) OVER (PARTITION BY week) AS n, "
    "row_number() OVER (PARTITION BY week ORDER BY dollars) AS by_dollars, "
    "row_number() OVER (PARTITION BY week ORDER BY units) AS by_units FROM own), "
    "costs AS (SELECT week, sum(dollars) AS own_dollars, avg(dollars) AS own_dollars_mean, "
    "avg(CASE WHEN by_dollars IN ((n + 1) / 2, (n + 2) / 2) THEN dollars END) "
    "AS own_dollars_median, avg(units) AS own_units_mean, "
    "avg(CASE WHEN by_units IN ((n + 1) / 2, (n + 2) / 2) THEN units END) AS own_units_median "
    "FROM ranked GROUP BY week), "
    "weeks AS (SELECT week, sum(judged AND redone_by IS NULL) AS merges, "
    "sum(NOT judged) AS waiting FROM redo_rows GROUP BY week), "
    f"spent AS (SELECT {WEEK.format(day=f"date(day, '+{REDO_DAYS} days')")} AS week, "
    f"sum(dollars) AS dollars FROM call_rows WHERE role IS NOT '{OTHER}' GROUP BY 1) "
    "SELECT w.week, w.merges, w.waiting, c.own_dollars, c.own_dollars_mean, "
    "c.own_dollars_median, c.own_units_mean, c.own_units_median, s.dollars AS all_in_dollars, "
    "s.dollars / nullif(w.merges, 0) AS all_in_per_merge "
    "FROM weeks w LEFT JOIN costs c ON c.week = w.week LEFT JOIN spent s ON s.week = w.week"
)
