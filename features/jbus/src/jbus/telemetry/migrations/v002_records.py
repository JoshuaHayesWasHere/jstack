"""The records jbus keeps of what its snapshots overwrite (`jbus.history`, `jbus.spent`), and
`word-sends.json`. `brief_versions` and `spend_rows` are written out as they were made, since
their sources have gained columns since (`v015_brief_pull`, `v020_spend_trigger`): a column a
source gains later is a migration of its own."""

from jbus.telemetry.migrations import tables

SQL = (
    "CREATE TABLE brief_versions (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, slug TEXT, "
    "sha TEXT, was TEXT, bytes INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX brief_versions_day ON brief_versions (day);\n"
    + tables("row_pulls", "runs", "spend_days")
    + "CREATE TABLE spend_rows (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, "
    "spent_on TEXT, role TEXT, slug TEXT, units INTEGER, runs INTEGER, input INTEGER, "
    "cached INTEGER, written INTEGER, output INTEGER, day TEXT, PRIMARY KEY (project, key)) "
    "WITHOUT ROWID;\n"
    "CREATE INDEX spend_rows_day ON spend_rows (day);\n"
    + tables("word_sends")
    + "CREATE INDEX brief_versions_slug ON brief_versions (project, slug, at);\n"
    "CREATE INDEX row_pulls_slug ON row_pulls (project, slug);\n"
    "CREATE INDEX runs_run ON runs (project, run, attempt);\n"
)
