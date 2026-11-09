"""Each scout, by its project and slug (`scout`), with the plan entry it researched and how the rows
of that entry stand: `merged` (a `lead_times` row), `open` (`queue.LIVE`) and `none` (over, or
stopped, with no merge). A scout is a thread whose title gives the role `scout`, of any session,
since jbus hands a finished scout's row to a crewmate at the same slug and its queue row then names
no role. Its entry is its queue row's (`queue.entry`: the row's `entry`, its `parent_entry`, or its
slug), or its own slug where the queue holds no row of it; the rows of an entry are the queue's
rows that are no scout's request, each of its own slug's entry where it names none."""

from jbus import queue

LIVE = f"({', '.join(repr(status) for status in queue.LIVE)})"
"""The statuses of an open row, `queue.LIVE`, as a list of SQL."""
ENTRY_ROWS = (
    "entry_rows AS (SELECT q.project, coalesce(q.entry, q.slug) AS entry, q.slug, q.status, "
    "m.slug IS NOT NULL AS merged FROM queue q LEFT JOIN merged_rows m "
    "ON m.project = q.project AND m.slug = q.slug WHERE coalesce(q.role, '') <> 'scout'), "
    "scouts AS (SELECT DISTINCT s.project, s.slug AS scout, coalesce(q.entry, s.slug) AS entry "
    "FROM sessions s LEFT JOIN queue q ON q.project = s.project AND q.slug = s.slug "
    "WHERE s.role = 'scout' AND s.project IS NOT NULL AND coalesce(s.slug, '') <> '')"
)
"""The queue's rows by their entry (`entry_rows`) and each scout's entry (`scouts`), over a
`merged_rows` of `lead_times`, which `row_spend` splits a scout's spend by too."""

SQL = (
    "WITH merged_rows AS MATERIALIZED (SELECT DISTINCT project, slug FROM lead_times), "
    f"{ENTRY_ROWS} "
    "SELECT s.project, s.scout, s.entry, count(CASE WHEN r.merged THEN 1 END) AS merged, "
    f"count(CASE WHEN NOT r.merged AND r.status IN {LIVE} THEN 1 END) AS open, "
    f"count(CASE WHEN NOT r.merged AND r.status NOT IN {LIVE} THEN 1 END) AS none "
    "FROM scouts s LEFT JOIN entry_rows r ON r.project = s.project AND r.entry = s.entry "
    "GROUP BY s.project, s.scout, s.entry"
)
