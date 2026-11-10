"""Each rise of an account's usage quota between two of the health look's readings of a window
(`health_readings`, `quota <instance> <window>`, the window as `span`), for the units an account
can run before it is capped. `rise` is the points the window gained since the reading before,
`prev`; where the window reset between them, the share fell and the rise is the new share alone.
Its rows are the machine's, under the project `''`.
"""

SQL = (
    "SELECT instance, span, prev, at, "
    "CASE WHEN value >= before THEN value - before ELSE value END AS rise "
    "FROM (SELECT instance, span, at, value, "
    "lag(at) OVER w AS prev, lag(value) OVER w AS before FROM ("
    "SELECT substr(reading, 7, length(reading) - 6 - length(span) - 1) AS instance, span, "
    "at, value FROM (SELECT reading, at, value, CASE WHEN reading LIKE '% seven_day' "
    "THEN 'seven_day' ELSE 'five_hour' END AS span FROM health_readings "
    "WHERE project = '' AND reading LIKE 'quota % %' AND value IS NOT NULL)) "
    "WINDOW w AS (PARTITION BY instance, span ORDER BY at)) "
    "WHERE prev IS NOT NULL"
)
