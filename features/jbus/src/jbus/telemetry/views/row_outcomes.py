"""What each row that is over (`queue.over`: `merged` or `done`) came to, as `outcome`: `merged`,
where it has a `lead_times` row; `no pull request asked`, where its last brief version's `pull` is
`none` or `ask`; else the end that version's last Result names (`jbus.outcome`): `carried`,
`nothing to change` or `dropped`. A version that names none, as one written before `history.brief`
kept the outcome does, falls back to the rule from before: `carried`, where a row whose go names
it as its parent (`queue.follows`) is merged or open (`queue.LIVE`), and `ended without one` for
the rest. The store keeps no `why`, so a `done` row that still waits on one counts as over. A
brief version written before its `pull` was kept has an empty one, and asks for nothing here."""

from jbus.telemetry.views.scout_rows import LIVE

SQL = (
    "WITH merged_rows AS MATERIALIZED (SELECT DISTINCT project, slug FROM lead_times), "
    "lasts AS (SELECT project, slug, pull, outcome FROM (SELECT project, slug, pull, outcome, "
    "row_number() OVER (PARTITION BY project, slug ORDER BY at DESC, key DESC) AS place "
    "FROM brief_versions) WHERE place = 1), "
    "carriers AS (SELECT DISTINCT f.project, f.follows AS slug FROM queue f "
    "LEFT JOIN merged_rows m ON m.project = f.project AND m.slug = f.slug "
    f"WHERE f.follows IS NOT NULL AND (m.slug IS NOT NULL OR f.status IN {LIVE})) "
    "SELECT q.project, q.slug, q.status, CASE WHEN m.slug IS NOT NULL THEN 'merged' "
    "WHEN p.pull IN ('none', 'ask') THEN 'no pull request asked' "
    "WHEN p.outcome IS NOT NULL THEN p.outcome "
    "WHEN c.slug IS NOT NULL THEN 'carried' ELSE 'ended without one' END AS outcome FROM queue q "
    "LEFT JOIN merged_rows m ON m.project = q.project AND m.slug = q.slug "
    "LEFT JOIN lasts p ON p.project = q.project AND p.slug = q.slug "
    "LEFT JOIN carriers c ON c.project = q.project AND c.slug = q.slug "
    "WHERE q.status IN ('merged', 'done')"
)
