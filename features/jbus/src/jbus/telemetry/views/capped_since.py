"""The first day of the reads of which instances are capped (`capped_reads`), before which no week
has its capped minutes."""

SQL = "SELECT min(day) AS day FROM capped_reads"
