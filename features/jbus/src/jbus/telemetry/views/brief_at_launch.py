"""Each launch of a row (fault F1), the sha of the brief stored then (`brief-versions.jsonl`), and
how many versions came after it."""

SQL = (
    "SELECT t.project, t.slug, t.at AS launched_at, t.day, (SELECT v.sha FROM brief_versions v "
    "WHERE v.project = t.project AND v.slug = t.slug AND v.at <= t.at "
    "ORDER BY v.at DESC, v.key DESC LIMIT 1) AS sha, (SELECT count(*) FROM brief_versions v "
    "WHERE v.project = t.project AND v.slug = t.slug AND v.at > t.at AND v.sha != '') "
    "AS changed_after FROM transitions t WHERE t.to_status = 'launched'"
)
