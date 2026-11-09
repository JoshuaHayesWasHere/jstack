"""Each launched row's seconds from its go to its launch, one row for each kind of reason it waited
for (`row_waits`): `hold`, `depends`, `red main`, `room`, `cap` or `none`.

The go is the earlier of the row's first approved item and its queue approval's `ran_at`, as
`lead_times` takes it, and the launch is its first move to `launched`. A reason holds from its
line of `waits.jsonl` to the row's next line. The time before the row's first line is `none`.
The time before the project's first line of `waits.jsonl` is not counted, since nothing kept a
reason then, so a row that launched before it has no row here. `at` and `day` are the launch's.
"""

SQL = (
    "WITH began AS (SELECT project, min(at) AS at FROM row_waits GROUP BY project), "
    "spans AS (SELECT l.project, l.slug, l.at AS stop, l.day, "
    "max(nullif(min(coalesce(g.approved, '~'), coalesce(q.approval_ran_at, '~')), '~'), b.at) "
    "AS start FROM row_moves l JOIN began b ON b.project = l.project "
    "LEFT JOIN row_goes g ON g.project = l.project AND g.slug = l.slug "
    "LEFT JOIN queue q ON q.project = l.project AND q.slug = l.slug "
    "WHERE l.to_status = 'launched' "
    "AND (g.approved IS NOT NULL OR q.approval_ran_at IS NOT NULL)), "
    "lines AS (SELECT project, slug, at, kind, "
    "lead(at) OVER (PARTITION BY project, slug ORDER BY at, key) AS next FROM row_waits), "
    "pieces AS (SELECT s.project, s.slug, s.stop, s.day, w.kind, max(w.at, s.start) AS a, "
    "min(coalesce(w.next, s.stop), s.stop) AS b FROM spans s JOIN lines w "
    "ON w.project = s.project AND w.slug = s.slug "
    "UNION ALL SELECT s.project, s.slug, s.stop, s.day, 'none', s.start, "
    "min(s.stop, coalesce((SELECT min(at) FROM row_waits w WHERE w.project = s.project "
    "AND w.slug = s.slug), s.stop)) FROM spans s) "
    "SELECT project, slug, kind, "
    "round(sum((julianday(b) - julianday(a)) * 86400.0), 1) AS seconds, stop AS at, day "
    "FROM pieces WHERE b > a GROUP BY project, slug, kind, stop, day"
)
