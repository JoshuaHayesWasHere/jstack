"""Each merged row of a project of `ci_projects`, `kept` where the store holds a push check of main
for its pull request."""

SQL = (
    "SELECT l.*, EXISTS (SELECT 1 FROM main_runs r WHERE r.project = l.project "
    "AND r.pr = l.pr) AS kept FROM lead_times l "
    "JOIN ci_projects p ON p.project = l.project WHERE l.pr IS NOT NULL"
)
