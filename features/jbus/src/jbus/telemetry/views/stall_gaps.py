"""Each day with rows merged before the stall record began (`stalls_since`), and how many: rows
whose quiet spells were not kept, which the stall minutes leave out."""

SQL = (
    "SELECT project, day, week, count(*) AS rows FROM lead_times "
    "WHERE day < (SELECT day FROM stalls_since) GROUP BY project, day"
)
