"""Each probe of a standing word in each run (`jbus.drift`), the machine's."""

SQL = (
    "CREATE TABLE drift (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, probe TEXT, "
    "word TEXT, status TEXT, found INTEGER, sha TEXT, error TEXT, day TEXT, "
    "PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX drift_at ON drift (at);\n"
)
