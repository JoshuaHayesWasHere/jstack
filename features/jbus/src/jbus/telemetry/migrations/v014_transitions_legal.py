"""Whether `queue.MOVES` holds a row's move: 0 for a line of `transitions.jsonl` that `derive`
marked `"legal": false`, 1 for any other. No line the store holds was marked, so each is 1, as a
rebuild reads it."""

SQL = "ALTER TABLE transitions ADD COLUMN legal INTEGER;\nUPDATE transitions SET legal = 1;\n"
