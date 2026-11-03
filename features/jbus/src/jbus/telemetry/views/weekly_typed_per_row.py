"""Each week's messages the user typed, not a resume (`ask_ledger`), over the rows merged in it
(`weekly_merges`)."""

SQL = (
    "WITH typed AS (SELECT week, count(*) AS typed FROM ask_ledger WHERE kind <> 'resume' "
    "GROUP BY week) SELECT m.week, coalesce(t.typed, 0) AS typed, m.merged, "
    "1.0 * coalesce(t.typed, 0) / m.merged AS per_row FROM weekly_merges m "
    "LEFT JOIN typed t ON t.week = m.week"
)
