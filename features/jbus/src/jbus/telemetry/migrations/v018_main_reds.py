"""Why main went red at each tip `jbus.mainmoved.tell` judged `failed` (`main-reds.jsonl`), as the
table was made, written out: a column added later is a migration of its own (`v022_main_reds_cause`)."""

SQL = (
    "CREATE TABLE main_reds (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, sha TEXT, "
    "pr INTEGER, step TEXT, tests INTEGER, verdict TEXT, day TEXT, PRIMARY KEY (project, key)) "
    "WITHOUT ROWID;\n"
    "CREATE INDEX main_reds_day ON main_reds (day);\n"
    "CREATE INDEX main_reds_sha ON main_reds (project, sha);\n"
)
