"""The shape of `calls` for SQLite's planner, in `sqlite_stat1`: a few providers, each with half
its calls, about fifty calls a session and about fifteen thousand a day.

A store with no statistics has the planner guess that `provider = ?` finds as few calls as
`provider = ? AND session = ?`, and then a join from `sessions` reads every call of a provider
once a session, by the primary key, which holds every column, and not the session's calls by
`calls_session`. On a store of 311756 calls that made the reads of `call_rows` by a week's crew
sessions, and `row_spend`'s calls of each scout, about 30 s each. The rows are written here and
not left to `ANALYZE calls`, which writes none for a new store's empty table: the shape holds at
any size. The first `ANALYZE sqlite_schema` makes `sqlite_stat1` where the store has none, and the
last loads the rows into the connection that runs this."""

SQL = (
    "ANALYZE sqlite_schema;\n"
    "DELETE FROM sqlite_stat1 WHERE tbl = 'calls';\n"
    "INSERT INTO sqlite_stat1 (tbl, idx, stat) VALUES "
    "('calls', 'calls', '300000 150000 1'), "
    "('calls', 'calls_session', '300000 150000 50'), "
    "('calls', 'calls_day', '300000 15000');\n"
    "ANALYZE sqlite_schema;\n"
)
