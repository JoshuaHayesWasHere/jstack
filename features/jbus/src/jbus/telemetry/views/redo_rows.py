"""Each merged row of `lead_times`, in the week its `REDO_DAYS` end, `judged` once they ended by
the last build, and the first row of `redos` that redid it in them: a redo after its merge and
within `REDO_DAYS`, or one with no time, since jbus reverts only main's red tip. A row redone
twice is one row."""

from jbus.telemetry.schema import WEEK

REDO_DAYS = 7
"""The days after its merge in which a later row's fix or revert makes a merged row redone."""
DUE = f"date(l.day, '+{REDO_DAYS} days')"
"""The local day a merged row's `REDO_DAYS` end on."""

SQL = (
    "WITH hits AS (SELECT l.project, l.slug, d.redoer, d.how, row_number() OVER "
    "(PARTITION BY l.project, l.slug ORDER BY d.at IS NULL, d.at, d.redoer) AS place "
    "FROM lead_times l JOIN redos d ON d.project = l.project AND d.slug = l.slug "
    "AND (d.at IS NULL OR (d.at >= l.merged_at AND julianday(d.at) <= "
    f"julianday(l.merged_at) + {REDO_DAYS}))) "
    "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, "
    f"{WEEK.format(day=DUE)} AS week, "
    f"coalesce(julianday(l.merged_at) + {REDO_DAYS} <= "
    "julianday((SELECT max(at) FROM builds)), 0) AS judged, h.redoer AS redone_by, h.how "
    "FROM lead_times l LEFT JOIN hits h ON h.project = l.project AND h.slug = l.slug "
    "AND h.place = 1"
)
