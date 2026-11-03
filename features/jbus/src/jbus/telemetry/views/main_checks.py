"""The latest run of each commit of `main_runs`, with when the commit's first run began
(`first`)."""

SQL = (
    "SELECT project, sha, pr, state, completed, first, day FROM (SELECT project, sha, pr, "
    "state, completed, min(created) OVER (PARTITION BY project, sha) AS first, "
    "min(day) OVER (PARTITION BY project, sha) AS day, row_number() OVER "
    "(PARTITION BY project, sha ORDER BY created DESC, run DESC) AS place FROM main_runs) "
    "WHERE place = 1"
)
