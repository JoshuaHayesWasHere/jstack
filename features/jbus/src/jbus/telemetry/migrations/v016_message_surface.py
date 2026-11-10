"""What each message the user typed is about (`jbus.telemetry.asks.surface`): the next build
reads every message of T3 Code's again to label it, since `messages.RULES` was raised with it,
and the cursor of `messages` goes so that it does even on a store whose rules were not signed."""

SQL = (
    "ALTER TABLE messages ADD COLUMN surface TEXT;\n"
    "DELETE FROM cursors WHERE source = 'messages';\n"
)
