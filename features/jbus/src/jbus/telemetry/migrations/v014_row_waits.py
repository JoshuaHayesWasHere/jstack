"""Each change of a row's reason to wait (`waits.jsonl`, `jbus.queue.derive`). The table is
written out as it was made, since its source has gained columns since (`v021_launch_failures`)."""

SQL = (
    "CREATE TABLE row_waits (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, slug TEXT, "
    "kind TEXT, why_len INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX row_waits_day ON row_waits (day);\n"
)
