"""Each `kept` row of `ci_rows` (S6), and whether its pull request opened a spell of `main_spells`
that a change caused: a spell whose `cause` is `change`, or `unjudged`, as every spell counted
before `main-reds.jsonl` began. A spell of a flake or of the infrastructure is no change failure. A
row whose push check was not kept could never fail, so it is not counted."""

SQL = (
    "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, l.week, EXISTS (SELECT 1 FROM "
    "main_spells s WHERE s.project = l.project AND s.start_pr = l.pr "
    "AND s.cause IN ('change', 'unjudged')) AS opened_spell "
    "FROM ci_rows l WHERE l.kept"
)
