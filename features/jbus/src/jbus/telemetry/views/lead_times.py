"""Each row whose pull request merged (S5), from its go to its merge, in minutes to four places,
since `julianday` is a float of days. The go is the earliest of the row's first approved item, its
queue approval's `ran_at` and its first launch, and the merge is `merged.json`'s `mergedAt`, else
the row's first move to `merged`."""

from jbus.telemetry.schema import WEEK

SQL = (
    "WITH rows AS (SELECT project, slug FROM transitions UNION SELECT project, slug FROM queue "
    "UNION SELECT project, slug FROM row_goes), "
    "ends AS (SELECT r.project, r.slug, coalesce(m.merged_at, t.at) AS merged_at, "
    "CASE WHEN m.merged_at IS NOT NULL THEN m.day ELSE t.day END AS day, "
    "coalesce(m.number, q.pr) AS pr, "
    "nullif(min(coalesce(g.approved, '~'), coalesce(q.approval_ran_at, '~'), "
    "coalesce(l.at, '~')), '~') AS go FROM rows r "
    "LEFT JOIN merged m ON m.project = r.project AND m.slug = r.slug "
    "LEFT JOIN row_moves t ON t.project = r.project AND t.slug = r.slug "
    "AND t.to_status = 'merged' "
    "LEFT JOIN row_moves l ON l.project = r.project AND l.slug = r.slug "
    "AND l.to_status = 'launched' "
    "LEFT JOIN queue q ON q.project = r.project AND q.slug = r.slug "
    "LEFT JOIN row_goes g ON g.project = r.project AND g.slug = r.slug) "
    "SELECT project, slug, pr, coalesce(go, merged_at) AS go, merged_at, day, "
    f"{WEEK.format(day='day')} AS week, "
    "round(max(0.0, (julianday(merged_at) - julianday(coalesce(go, merged_at))) * 1440.0), "
    "4) AS minutes FROM ends WHERE merged_at IS NOT NULL"
)
