"""The first day of jbus's row records (`items.jsonl`), before which no week has its rows: a week
that begins before it would count only part of itself."""

SQL = "SELECT min(day) AS day FROM items"
