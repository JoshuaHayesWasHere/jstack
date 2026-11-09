"""The session that queued a row (`queue.json`'s `queued_by.session`), and the message its go
rests on (`approval.message` for an entry's go, `approval.ref` for the user's message or pick):
what joins a row to the tokens of the home that queued it and to the message of its go. The
queue is read again on the next build, so each row it already holds gets both."""

SQL = (
    "ALTER TABLE queue ADD COLUMN queued_by_session TEXT;\n"
    "ALTER TABLE queue ADD COLUMN approval_message TEXT;\n"
    "DELETE FROM cursors WHERE source = 'queue';\n"
)
