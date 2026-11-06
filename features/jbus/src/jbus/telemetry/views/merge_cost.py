"""Each successful merge's own spend by the role, model and reasoning effort of the calls of its
threads: calls, the four raw counts, units, dollars, and the `unpriced` calls that have none. A
successful merge is a row of `redo_rows` whose 7 days are over (`judged`) and that no later row
redid. `week` is the one its 7 days end in, as `redo_rows` gives it. A Codex call has no effort and
no dollars.

The successful merges are found once, before the join (`MATERIALIZED`): left to itself, SQLite
folds `redo_rows` into the join and works out each row's `judged` and `redone_by` again for
every call of it, which takes the view from under a second to many."""

SQL = (
    "WITH r AS MATERIALIZED (SELECT * FROM redo_rows WHERE judged AND redone_by IS NULL) "
    "SELECT r.project, r.slug, r.pr, r.merged_at, r.week, c.role, c.provider, c.model, c.effort, "
    "count(*) AS calls, sum(c.input) AS input, sum(c.cache_write) AS cache_write, "
    "sum(c.cache_read) AS cache_read, sum(c.output) AS output, sum(c.units) AS units, "
    "sum(c.dollars) AS dollars, sum(c.dollars IS NULL) AS unpriced "
    "FROM r JOIN call_rows c ON c.project = r.project AND c.slug = r.slug "
    "GROUP BY r.project, r.slug, c.role, c.provider, c.model, c.effort"
)
