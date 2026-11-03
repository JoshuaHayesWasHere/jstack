"""Each agent call's token usage, and the thread of each session (`tokens`)."""

SQL = (
    "CREATE TABLE sessions (provider TEXT NOT NULL, session TEXT NOT NULL, thread TEXT, "
    "instance TEXT, project TEXT, role TEXT, slug TEXT, PRIMARY KEY (provider, session)) "
    "WITHOUT ROWID;\n"
    "CREATE INDEX sessions_row ON sessions (project, slug);\n"
    "CREATE TABLE calls (provider TEXT NOT NULL, call TEXT NOT NULL, session TEXT NOT NULL, "
    "agent TEXT, at TEXT, model TEXT, input INTEGER NOT NULL, cache_write INTEGER NOT NULL, "
    "cache_read INTEGER NOT NULL, output INTEGER NOT NULL, final INTEGER NOT NULL, day TEXT, "
    "PRIMARY KEY (provider, call)) WITHOUT ROWID;\n"
    "CREATE INDEX calls_session ON calls (provider, session);\n"
    "CREATE INDEX calls_day ON calls (day);\n"
)
