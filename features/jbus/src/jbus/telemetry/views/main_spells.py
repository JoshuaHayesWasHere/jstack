"""Each red spell of main's push checks, from the first commit whose check failed to the next commit
whose check passed (`minutes_to_green`)."""

from jbus.telemetry.schema import WEEK

SQL = (
    "WITH judged AS (SELECT * FROM main_checks WHERE state IN ('red', 'green')), "
    "marked AS (SELECT *, CASE WHEN state = 'red' AND coalesce(lag(state) OVER "
    "(PARTITION BY project ORDER BY first, sha), 'green') = 'green' THEN 1 ELSE 0 END "
    "AS opens FROM judged), "
    "grouped AS (SELECT *, sum(opens) OVER (PARTITION BY project ORDER BY first, sha "
    "ROWS UNBOUNDED PRECEDING) AS spell FROM marked), "
    "ends AS (SELECT project, spell, completed AS green_at, sha AS end_sha, row_number() "
    "OVER (PARTITION BY project, spell ORDER BY first, sha) AS place FROM grouped "
    "WHERE state = 'green' AND spell > 0) "
    "SELECT g.project, g.spell, g.pr AS start_pr, g.sha AS start_sha, "
    "g.completed AS first_fail_at, g.day, "
    f"{WEEK.format(day='g.day')} AS week, e.end_sha, e.green_at, "
    "round((julianday(e.green_at) - julianday(g.completed)) * 1440.0, 1) "
    "AS minutes_to_green FROM grouped g "
    "LEFT JOIN ends e ON e.project = g.project AND e.spell = g.spell AND e.place = 1 "
    "WHERE g.opens = 1"
)
