"""Each row's first move to each status (`transitions.jsonl`)."""

SQL = (
    "SELECT project, slug, to_status, at, day FROM (SELECT project, slug, to_status, at, day, "
    "row_number() OVER (PARTITION BY project, slug, to_status ORDER BY at, key) AS place "
    "FROM transitions) WHERE place = 1"
)
