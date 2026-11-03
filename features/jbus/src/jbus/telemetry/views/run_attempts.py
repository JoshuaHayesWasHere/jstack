"""Each workflow run of every project (fault F2), its attempts, when and at which attempt it first
failed, and how its last attempt ended (`runs.jsonl`)."""

from jbus.telemetry.schema import RED

SQL = (
    "SELECT project, run, max(workflow) AS workflow, max(sha) AS sha, max(branch) AS branch, "
    "max(event) AS event, max(pr) AS pr, count(*) AS attempts, min(day) AS day, "
    f"min(CASE WHEN conclusion IN {RED} THEN updated END) AS first_fail_at, "
    f"min(CASE WHEN conclusion IN {RED} THEN attempt END) AS first_fail_attempt, "
    "max(updated) AS last_at, (SELECT r.conclusion FROM runs r WHERE r.project = runs.project "
    "AND r.run = runs.run ORDER BY r.attempt DESC LIMIT 1) AS last_conclusion "
    "FROM runs GROUP BY project, run"
)
