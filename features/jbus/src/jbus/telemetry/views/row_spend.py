"""Each merged row's spend by the role and the provider of the threads that spent it: calls, the
four counts, units, dollars, and the `unpriced` calls that have none.

A call of a crewmate, a reviewer or any thread but a home's or a scout's is its own slug's. A
home's call is the next row its thread queued (`row_causes`' `QUEUED`: the least `briefed` at or
after the call), so a home resumed on a new session still finds the rows it queued. That row is
looked up once a call, by its thread and by its session, and not found by pairing the call with
every later row its thread queued, which was a million pairs on a store of 26 thousand home calls.
A scout's call is split evenly over the merged rows of its entry (`scout_rows`), and each of its
sums, `calls` and `unpriced` too, is its share, so a scout's spend sums back once over the rows. A
home's call after the last row its thread queued, and a scout's whose entry has no merged row, are
no row's."""

from jbus.telemetry.views.row_causes import QUEUED
from jbus.telemetry.views.scout_rows import ENTRY_ROWS

CALL = (
    "c.project, c.role, c.provider, c.model, c.input, c.cache_write, c.cache_read, c.output, "
    "c.units, "
)
"""The columns of a call that a row's spend sums, and its model, before its row and its share."""

OWNED = (
    "merged_rows AS MATERIALIZED (SELECT project, slug, pr, merged_at, day, week "
    "FROM lead_times), "
    f"{ENTRY_ROWS}, "
    f"{QUEUED}, "
    "causes AS MATERIALIZED (SELECT project, slug, session, thread, briefed FROM queued "
    "WHERE briefed IS NOT NULL), "
    f"homed AS (SELECT {CALL}c.dollars, (SELECT slug FROM (SELECT r.briefed, r.slug "
    "FROM causes r WHERE r.project = c.project AND r.thread = c.thread AND r.briefed >= c.at "
    "UNION ALL SELECT r.briefed, r.slug FROM causes r WHERE r.project = c.project "
    "AND r.session = c.session AND r.briefed >= c.at) ORDER BY briefed, slug LIMIT 1) AS slug "
    "FROM call_rows c WHERE c.role = 'home'), "
    "split AS (SELECT s.project, s.scout, r.slug, 1.0 / s.merged AS share FROM scout_rows s "
    "JOIN entry_rows r ON r.project = s.project AND r.entry = s.entry AND r.merged "
    "WHERE s.merged > 0), "
    f"owned AS (SELECT {CALL}c.dollars, c.slug, 1 AS share FROM call_rows c "
    "WHERE coalesce(c.role, '') NOT IN ('home', 'scout') "
    "UNION ALL SELECT project, role, provider, model, input, cache_write, cache_read, output, "
    "units, dollars, slug, 1 FROM homed WHERE slug IS NOT NULL "
    f"UNION ALL SELECT {CALL}c.dollars, s.slug, s.share FROM call_rows c JOIN split s "
    "ON s.project = c.project AND s.scout = c.slug WHERE c.role = 'scout')"
)
"""The CTEs that give each call its merged row: `merged_rows`, of `lead_times`, and `owned`, each
call of a row with its role, provider, model, the four counts, units, dollars, `slug` and `share`,
the part of the call the row counts. `weekly_unpriced` reads them too, so the calls it names are
the calls this view's `unpriced` counts."""

SQL = (
    f"WITH {OWNED} "
    "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, l.week, o.role, o.provider, "
    "sum(o.share) AS calls, sum(o.input * o.share) AS input, "
    "sum(o.cache_write * o.share) AS cache_write, sum(o.cache_read * o.share) AS cache_read, "
    "sum(o.output * o.share) AS output, sum(o.units * o.share) AS units, "
    "sum(o.dollars * o.share) AS dollars, sum((o.dollars IS NULL) * o.share) AS unpriced "
    "FROM merged_rows l JOIN owned o ON o.project = l.project AND o.slug = l.slug "
    "GROUP BY l.project, l.slug, o.role, o.provider"
)

WAKE = ("slot-wake", "slot-end", "pool-wake", "run-wake", "clock")
"""The send keys of a wake (`jbus.outbox.WAKES`): a wake is its own class, before the row's first
prereview and after it."""
CHECK = ("failed", "refailed")
"""The send keys of a failed check of the row's pull request."""
STALE = (
    "rebase",
    "restack",
    "drops",
    "proved-stale",
    "proved-unnamed",
    "merged-tree",
    "mainmoved",
    "conflict",
    "rewritten",
    "reload",
    "restart",
)
"""The send keys of a stale base: main moved, a link moved, or a proof is of another tree."""


def _keys(keys: tuple[str, ...]) -> str:
    return ", ".join(f"'{key}'" for key in keys)


CLASSES = (
    "crew_lines AS (SELECT s.project, s.slug, s.spent_on, s.trigger AS woke, s.reviewed, "
    "s.dollars FROM spend_rows s WHERE s.role = 'crew' AND s.slug IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM spend_rows o WHERE o.project = s.project "
    "AND o.slug = s.slug AND o.role = 'crew' AND o.trigger IS NULL)), "
    "first_prereview AS (SELECT project, slug, min(spent_on) AS spent_on FROM crew_lines "
    "WHERE woke = 'prereviewed' GROUP BY project, slug), "
    "crew_classes AS (SELECT c.project, c.slug, CASE "
    "WHEN c.woke = 'prereviewed' THEN 'prereview fix' "
    f"WHEN c.woke IN ({_keys(WAKE)}) THEN 'wake' "
    "WHEN NOT (coalesce(c.reviewed, 0) OR coalesce(f.spent_on < c.spent_on, 0)) THEN 'build' "
    f"WHEN c.woke IN ({_keys(CHECK)}) THEN 'failed check' "
    f"WHEN c.woke IN ({_keys(STALE)}) THEN 'stale base' "
    "ELSE 'other' END AS class, c.dollars FROM crew_lines c "
    "LEFT JOIN first_prereview f ON f.project = c.project AND f.slug = c.slug)"
)
"""The CTEs that give each crew line of `spend_rows` its class, what woke its runs:
`prereview fix`, `wake`, `build` for any other before the row's first prereview (a `lapse` resume
too), then `failed check`, `stale base` or `other`. A row with any crew line kept before the
trigger was has no class at all, since its first prereview may be on such a line. A line is
after the first prereview where its runs came after one that day (`reviewed`), or its day is
after the first day a prereview woke the row's crew. A run the user or a harness notice woke has
no send key, and is `build` or `other` by when it ran."""
