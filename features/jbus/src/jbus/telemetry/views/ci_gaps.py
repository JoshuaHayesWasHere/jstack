"""Each day with merged rows of `ci_rows` that are not `kept`, and how many."""

SQL = (
    "SELECT project, day, week, count(*) AS rows FROM ci_rows WHERE NOT kept GROUP BY project, day"
)
