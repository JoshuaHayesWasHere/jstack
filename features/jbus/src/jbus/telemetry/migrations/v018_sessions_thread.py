"""An index of `sessions` by thread, so the last call of one thread (`jbus.compact.last_call`) is
read from that thread's sessions and not from a scan of every call. `IF NOT EXISTS`, since the
index is on a table an earlier migration made, which a store rewound past this one still has."""

SQL = "CREATE INDEX IF NOT EXISTS sessions_thread ON sessions (thread);\n"
