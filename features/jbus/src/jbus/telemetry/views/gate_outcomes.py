"""Each gate label of a week's file (`labels`), who closed its gate (`questions.closed_by`), and
whether its outcome is known and wrong, as `features/jbus/docs/jbus/gate-labels.md` says: `stood`,
`corrected` and `other_done` are known, and `corrected` and `other_done` say the chosen option did
not stand. The store keeps a gate that has left `questions.json`, where the weekly report
(`jbus.ci.wrongcloses`) no longer finds it."""

KNOWN = "('stood', 'corrected', 'other_done')"
WRONG = "('corrected', 'other_done')"

SQL = (
    "SELECT g.week, g.key, g.outcome, q.closed_by, "
    f"coalesce(g.outcome IN {KNOWN}, 0) AS known, "
    f"coalesce(g.outcome IN {WRONG}, 0) AS wrong FROM gate_labels g "
    "LEFT JOIN questions q ON q.project || '#' || q.number = g.key"
)
