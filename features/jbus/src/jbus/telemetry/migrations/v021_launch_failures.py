"""Each launch failure or wait by its cause (`jbus.telemetry.launch_failures`): the cause of each
`events` line and each `row_waits` line, read again from the start of each `events.jsonl` and
`waits.jsonl` as their cursors go, and the table a build makes of them."""

SQL = (
    "ALTER TABLE events ADD COLUMN launch_cause TEXT;\n"
    "ALTER TABLE row_waits ADD COLUMN launch_cause TEXT;\n"
    "ALTER TABLE row_waits ADD COLUMN launch_reason TEXT;\n"
    "DELETE FROM cursors WHERE source IN ('events', 'row_waits');\n"
    "CREATE TABLE launch_failures (project TEXT NOT NULL, key TEXT NOT NULL, slug TEXT, "
    'cause TEXT, reason TEXT, start TEXT, "end" TEXT, minutes REAL, day TEXT, '
    "PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX launch_failures_cause ON launch_failures (cause, start);\n"
)
