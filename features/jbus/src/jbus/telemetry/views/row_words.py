"""Each merged row with a go (S1), and the messages the user typed (`ask_ledger`, not a resume)
after its go and by its merge that name it: one an act of the row's project on the row cites, or one
typed in the row's own thread (`queue.thread`, the crew's)."""

SQL = (
    "SELECT l.project, l.slug, l.week, (SELECT count(*) FROM ask_ledger k "
    "WHERE k.kind <> 'resume' AND k.at > l.go AND k.at <= l.merged_at AND ("
    "EXISTS (SELECT 1 FROM acts a WHERE a.id = k.link AND a.project = l.project "
    "AND a.subject = l.slug) OR EXISTS (SELECT 1 FROM queue q WHERE q.project = l.project "
    "AND q.slug = l.slug AND q.thread = k.thread))) AS words "
    "FROM lead_times l WHERE l.go < l.merged_at"
)
