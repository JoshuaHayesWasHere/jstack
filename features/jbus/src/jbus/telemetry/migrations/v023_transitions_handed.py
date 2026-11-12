"""Whether a line of `transitions.jsonl` is a scout's done row handed to its crewmate: 1 for a
line `jbus.queue._hand_over` marked `"handed": true`, 0 for any other. No line the store held
before it was marked, so each is 0, as a rebuild reads it."""

SQL = "ALTER TABLE transitions ADD COLUMN handed INTEGER NOT NULL DEFAULT 0;\n"
