"""What a message the user typed asks (`jbus.telemetry.asks`), now that a mention in backticks or
parentheses is no ask: the next build reads every `acts.jsonl` again to label each word anew, and
every message of T3 Code's, since `messages.RULES` was raised with it."""

SQL = "DELETE FROM cursors WHERE source = 'acts';\n"
