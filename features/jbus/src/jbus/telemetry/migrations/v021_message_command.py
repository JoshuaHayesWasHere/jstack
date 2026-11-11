"""The command each user's message opens with, and whether it is a door, a skill or a built-in
(`jbus.telemetry.messages.command`): the next build reads every message of T3 Code's again to
label it, since `messages.RULES` was raised with it, and the cursor of `messages` goes so that it
does even on a store whose rules were not signed."""

SQL = (
    "ALTER TABLE messages ADD COLUMN command TEXT;\n"
    "ALTER TABLE messages ADD COLUMN command_kind TEXT;\n"
    "DELETE FROM cursors WHERE source = 'messages';\n"
)
