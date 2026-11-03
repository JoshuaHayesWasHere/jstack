"""Each merge week's units of `row_spend` over its merged rows with any call recorded, in millions.
A row whose transcripts went before a build read them counts low."""

SQL = (
    "SELECT week, count(DISTINCT project || '/' || slug) AS rows, sum(units) AS units, "
    "sum(units) / count(DISTINCT project || '/' || slug) / 1e6 AS per_row FROM row_spend "
    "GROUP BY week"
)
