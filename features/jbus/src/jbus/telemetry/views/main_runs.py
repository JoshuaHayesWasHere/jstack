"""The push checks on main that `ci.jsonl` holds: the latest attempt of each run, and whether it is
red, green or still pending."""

from jbus.telemetry.schema import GREEN, RED

SQL = (
    "WITH last AS (SELECT project, run, max(attempt) AS attempt FROM ci_jobs "
    "WHERE branch = 'main' AND event = 'push' GROUP BY project, run) "
    "SELECT j.project, j.run, j.attempt, max(j.sha) AS sha, max(j.pr) AS pr, "
    "min(j.created) AS created, max(j.completed) AS completed, min(j.day) AS day, "
    f"CASE WHEN sum(j.conclusion IN {RED}) > 0 THEN 'red' "
    f"WHEN sum(coalesce(j.conclusion, '') NOT IN {GREEN}) = 0 THEN 'green' "
    "ELSE 'pending' END AS state "
    "FROM ci_jobs j JOIN last ON last.project = j.project AND last.run = j.run "
    "AND last.attempt = j.attempt GROUP BY j.project, j.run, j.attempt"
)
