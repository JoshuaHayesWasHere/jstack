"""The first day of a follow-up's go that names its parent, before which no fix but a
`main-red-<sha12>` one names the row it redoes."""

SQL = "SELECT min(day) AS day FROM queue WHERE follows IS NOT NULL"
