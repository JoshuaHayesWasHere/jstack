"""Each merged row's spend by the role and the provider of the threads that spent it: calls, the
four counts and units."""

SQL = (
    "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, l.week, c.role, c.provider, "
    "count(*) AS calls, sum(c.input) AS input, sum(c.cache_write) AS cache_write, "
    "sum(c.cache_read) AS cache_read, sum(c.output) AS output, sum(c.units) AS units "
    "FROM lead_times l JOIN call_rows c ON c.project = l.project AND c.slug = l.slug "
    "GROUP BY l.project, l.slug, c.role, c.provider"
)
