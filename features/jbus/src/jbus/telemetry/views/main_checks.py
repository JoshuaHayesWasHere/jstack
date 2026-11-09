"""The latest run of the `check` workflow for each commit of `main_runs`, with when the commit's
first such run began (`first`). The store keeps no workflow name, so a run of `check` is one with a
job named `check`: the macos workflow's runs at the same commit would otherwise hide check's red."""

SQL = (
    "SELECT project, sha, pr, state, completed, first, day FROM (SELECT project, sha, pr, "
    "state, completed, min(created) OVER (PARTITION BY project, sha) AS first, "
    "min(day) OVER (PARTITION BY project, sha) AS day, row_number() OVER "
    "(PARTITION BY project, sha ORDER BY created DESC, run DESC) AS place FROM main_runs r "
    "WHERE EXISTS (SELECT 1 FROM ci_jobs j WHERE j.project = r.project AND j.run = r.run "
    "AND j.name = 'check')) WHERE place = 1"
)
