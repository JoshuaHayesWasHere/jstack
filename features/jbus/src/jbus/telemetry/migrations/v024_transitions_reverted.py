"""Whether a line of `transitions.jsonl` is a merged row opened again because the revert jbus
opened of its merge merged: 1 for a line `jbus.queue.reland` marked with the revert's address
under `reverted`, 0 for any other. No line the store held before it was marked, so each is 0, as a
rebuild reads it."""

SQL = "ALTER TABLE transitions ADD COLUMN reverted INTEGER NOT NULL DEFAULT 0;\n"
