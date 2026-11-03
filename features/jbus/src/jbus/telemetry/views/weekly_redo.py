"""Each week's rows of `redo_rows`: those redone among the judged ones, the judged ones, those
whose 7 days are not over (`waiting`), and the rate, of the judged ones."""

SQL = (
    "SELECT week, sum(judged AND redone_by IS NOT NULL) AS redone, sum(judged) AS judged, "
    "sum(NOT judged) AS waiting, "
    "100.0 * sum(judged AND redone_by IS NOT NULL) / nullif(sum(judged), 0) AS rate "
    "FROM redo_rows GROUP BY week"
)
