"""Each merge week's units of `row_spend` over its merged rows with any call recorded, in millions,
and its dollars over the same rows (`dollars_per_row`), with its `unpriced` calls. A row whose
transcripts went before a build read them counts low."""

SQL = (
    "SELECT project, week, count(DISTINCT project || '/' || slug) AS rows, sum(units) AS units, "
    "sum(units) / count(DISTINCT project || '/' || slug) / 1e6 AS per_row, "
    "sum(dollars) AS dollars, sum(unpriced) AS unpriced, "
    "sum(dollars) / count(DISTINCT project || '/' || slug) AS dollars_per_row "
    "FROM row_spend GROUP BY project, week"
)
