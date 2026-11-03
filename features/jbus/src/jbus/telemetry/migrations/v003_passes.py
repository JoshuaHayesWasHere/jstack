"""Whether jbus read an act's words in T3 Code itself (`party.Evidence.checked`), and each pass's
seconds, the machine's, under the project `''`. An act a store read before this has no `checked`."""

SQL = (
    "ALTER TABLE acts ADD COLUMN checked INTEGER;\n"
    "CREATE TABLE passes (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, seconds REAL, "
    "day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX passes_at ON passes (at);\n"
)
