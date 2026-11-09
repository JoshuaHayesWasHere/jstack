"""Each gate's label of a week (`labels`), the first home's by name where two homes label one
gate, so a build read on counts what a build from nothing does; its project, the key's part
before its `#`; who closed the gate (`questions.closed_by`); and whether its outcome is known and
wrong, as
`features/jbus/docs/jbus/gate-labels.md` says: `stood`, `corrected` and `other_done` are known,
and `corrected` and `other_done` say the chosen option did not stand. The store keeps a gate that
has left `questions.json`, where the weekly report (`jbus.ci.wrongcloses`) no longer finds it."""

KNOWN = "('stood', 'corrected', 'other_done')"
WRONG = "('corrected', 'other_done')"

SQL = (
    "WITH first AS (SELECT week, key, outcome FROM (SELECT *, row_number() OVER "
    "(PARTITION BY week, key ORDER BY home) AS place FROM gate_labels) WHERE place = 1) "
    "SELECT substr(g.key, 1, instr(g.key, '#') - 1) AS project, g.week, g.key, g.outcome, "
    "q.closed_by, "
    f"coalesce(g.outcome IN {KNOWN}, 0) AS known, "
    f"coalesce(g.outcome IN {WRONG}, 0) AS wrong FROM first g "
    "LEFT JOIN questions q ON q.project || '#' || q.number = g.key"
)
