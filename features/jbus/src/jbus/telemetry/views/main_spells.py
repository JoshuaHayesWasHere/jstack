"""Each red spell of main's push checks, from the first commit whose check failed to the next commit
whose check passed (`minutes_to_green`), and its `cause`, from the lines `jbus.mainmoved.tell`
wrote for the spell's first red commit in `main-reds.jsonl`.

The line that closed the spell decides where there is one: `no fix`, no fix row and no revert
merged before main went green, is `flake`, and a fix (`fix: #<n>`) is `change` where the first
verdict was `flake`. Otherwise `cause` is the verdict at the first red commit (`change`, `flake`
or `infra`), or `unjudged` where it wrote none, as for a spell before the ledger began."""

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
    "WHERE state = 'green' AND spell > 0), "
    "spells AS (SELECT g.project, g.spell, g.pr AS start_pr, g.sha AS start_sha, "
    "g.completed AS first_fail_at, g.day, "
    f"{WEEK.format(day='g.day')} AS week, e.end_sha, e.green_at, "
    "round((julianday(e.green_at) - julianday(g.completed)) * 1440.0, 1) "
    "AS minutes_to_green, (SELECT r.verdict FROM main_reds r WHERE r.project = g.project "
    "AND r.sha = g.sha AND r.verdict IS NOT NULL ORDER BY r.at DESC LIMIT 1) AS judged, "
    "(SELECT r.cause FROM main_reds r WHERE r.project = g.project AND r.sha = g.sha "
    "AND r.cause IS NOT NULL ORDER BY r.at DESC LIMIT 1) AS closed "
    "FROM grouped g "
    "LEFT JOIN ends e ON e.project = g.project AND e.spell = g.spell AND e.place = 1 "
    "WHERE g.opens = 1) "
    "SELECT project, spell, start_pr, start_sha, first_fail_at, day, week, end_sha, green_at, "
    "minutes_to_green, CASE WHEN closed = 'no fix' THEN 'flake' "
    "WHEN closed LIKE 'fix:%' AND judged = 'flake' THEN 'change' "
    "ELSE coalesce(judged, 'unjudged') END AS cause FROM spells"
)
