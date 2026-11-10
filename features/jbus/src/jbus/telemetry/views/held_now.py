"""Each ready pull request that waits for `jmerge` now (`open_waits`), with `held`, the seconds
its blocker `row-held` has held it: those of its closed segments, and where its open segment is
`row-held`, the seconds from `seen` to the last build. A pull request whose merge began at the
same head (`merge_waits`) waits no more, even before the next read of `merge-waits.json`."""

SQL = (
    "SELECT w.project, w.number AS pr, w.head, w.ready, w.code, w.seen, "
    "round(coalesce(json_extract(w.blockers, '$.\"row-held\"'), 0) "
    "+ CASE WHEN w.code = 'row-held' AND w.seen IS NOT NULL THEN coalesce(max(0, "
    "(julianday((SELECT max(at) FROM builds)) - julianday(w.seen)) * 86400.0), 0) ELSE 0 END, 3) "
    "AS held "
    "FROM open_waits w WHERE w.number IS NOT NULL AND NOT EXISTS (SELECT 1 FROM merge_waits m "
    "WHERE m.project = w.project AND m.number = w.number AND m.head IS w.head)"
)
