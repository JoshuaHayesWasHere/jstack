"""Each row's go: the first `approved` record of its items, by the slug the record names or the one
its item first named (`item_slugs`)."""

SQL = (
    "SELECT i.project, coalesce(i.slug, s.slug) AS slug, min(i.at) AS approved FROM items i "
    "LEFT JOIN item_slugs s ON s.project = i.project AND s.item = i.item "
    "WHERE i.verb = 'approved' AND coalesce(i.slug, s.slug) IS NOT NULL GROUP BY 1, 2"
)
