"""The messages of T3 Code's threads (`jbus.telemetry.messages`) as the table was made, written
out, and the index by which an act finds the message it cites."""

SQL = (
    "CREATE TABLE messages (project TEXT NOT NULL, key TEXT NOT NULL, id TEXT, thread TEXT, "
    "role TEXT, at TEXT, project_id TEXT, created_by TEXT, creation_source TEXT, kind TEXT, "
    "text_len INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX messages_day ON messages (day);\n"
    "CREATE INDEX messages_thread ON messages (thread, role, at);\n"
    "CREATE INDEX messages_key ON messages (key);\n"
    "CREATE INDEX acts_ref ON acts (ref);\n"
)
