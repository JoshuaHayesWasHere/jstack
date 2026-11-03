"""The slug of each item of jbus's row records (`items.jsonl`), from the first of its records that
names one."""

SQL = (
    "SELECT project, item, slug FROM (SELECT project, item, slug, row_number() OVER "
    "(PARTITION BY project, item ORDER BY at, key) AS place FROM items "
    "WHERE slug IS NOT NULL) WHERE place = 1"
)
