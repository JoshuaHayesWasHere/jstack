"""What each message the user typed asks (`jbus.telemetry.asks`), and each word of `acts`: the
next build reads every `acts.jsonl` again to label the words the store holds, and every message
of T3 Code's, since `messages.RULES` was raised with it."""

SQL = (
    "ALTER TABLE messages ADD COLUMN asks TEXT;\n"
    "ALTER TABLE acts ADD COLUMN asks TEXT;\n"
    "DELETE FROM cursors WHERE source = 'acts';\n"
)
