"""Each week's rows `merged` since the stall record began (`stalls_since`), the `minutes` and
`spells` of `stall_spells` that ended in it, and `per_row`: a week with merged rows and no spell
is 0."""

SQL = (
    "WITH merged AS (SELECT week, count(*) AS merged FROM lead_times "
    "WHERE day >= (SELECT day FROM stalls_since) GROUP BY week), "
    "quiet AS (SELECT week, sum(minutes) AS minutes, count(*) AS spells FROM stall_spells "
    "GROUP BY week) "
    "SELECT m.week, m.merged, coalesce(q.minutes, 0) AS minutes, "
    "coalesce(q.spells, 0) AS spells, coalesce(q.minutes, 0) / m.merged AS per_row "
    "FROM merged m LEFT JOIN quiet q ON q.week = m.week"
)
