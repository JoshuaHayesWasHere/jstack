"""Each later row that redoes a merged row, with `how` and when (`at`): a `follow-up`, or a
`main-red` fix, whose go names its parent (`queue.follows`), when the rule approved it; a
`main-red-<sha12>` fix that names no parent, of the row whose merge commit that red tip is; and a
`revert` jbus opened of its culprit (`reverts`), when its pull request opened (`ci_prs`), or no
time where the store keeps none of it."""

SQL = (
    "SELECT project, slug AS redoer, CASE WHEN slug LIKE 'main-red-%' THEN 'main-red' "
    "ELSE 'follow-up' END AS how, follows AS slug, approval_ran_at AS at FROM queue "
    "WHERE follows IS NOT NULL "
    "UNION ALL SELECT q.project, q.slug, 'main-red', m.slug, q.approval_ran_at FROM queue q "
    "JOIN merged m ON m.project = q.project AND substr(m.merge_commit, 1, 12) = "
    f"substr(q.slug, 10) WHERE q.follows IS NULL AND q.slug GLOB 'main-red-{'[0-9a-f]' * 12}' "
    "UNION ALL SELECT r.project, r.branch, 'revert', r.slug, c.created FROM reverts r "
    "LEFT JOIN ci_prs c ON c.project = r.project AND c.number = r.pr"
)
