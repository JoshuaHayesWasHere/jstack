"""The store's tables, how a store of an older schema is brought up to this one, and its views.

`PRAGMA user_version` is the schema's version: `MIGRATIONS[n]` takes a store from version `n`
to `n + 1`, and `migrate` runs the ones a store has not had, each once, in one transaction with
its new version. The store holds rows its sources no longer have (the daily trim, a snapshot's
dropped record), so it is never dropped and built again: a change to a table is a new migration
at the end of the list, such as `ALTER TABLE <t> ADD COLUMN <c>`.

The views hold no rows, so `VIEWS` is dropped and made again on each build: a change to a view
is a change here and nothing else.

KPI views, with the scorecard's definitions (`reports/week-audit/scorecard.py` in the home):

- `lead_times` (S5): each row whose pull request merged, from its go to its merge, in minutes to
  four places, since `julianday` is a float of days. The go is
  the earliest of the row's first approved item, its queue approval's `ran_at` and its first
  launch, and the merge is `merged.json`'s `mergedAt`, else the row's first move to `merged`.
- `main_runs`, `main_checks` and `main_spells`: the push checks on main that `ci.jsonl` holds,
  the latest attempt of each run, the latest run of each commit, and each red spell from the
  first commit whose check failed to the next commit whose check passed (`minutes_to_green`).
- `change_failures` (S6): each merged row, and whether its pull request opened a spell.
- `brief_at_launch` (fault F1): each launch of a row, the sha of the brief stored then
  (`brief-versions.jsonl`), and how many versions came after it.
- `run_attempts` (fault F2): each workflow run of every project, its attempts, when and at which
  attempt it first failed, and how its last attempt ended (`runs.jsonl`).
- `carried_words` (fault F4): each word the user had a home carry (`acts.jsonl`'s `word`), and
  the thread it went to and when (`word-sends.json`), with no word of its text.
- `weekly_lead_time`, `weekly_change_failure` and `weekly_restore` (S7): each week's number,
  the median and the 85th percentile as `statistics.median` and the scorecard's `pct` take
  them. A week starts on Sunday, in the user's zone.
"""

from __future__ import annotations

from jbus.telemetry.records import SOURCES, Source


def _table(source: Source) -> str:
    """The SQL that makes a source's table."""
    columns = ", ".join(f"{name} {kind}" for name, kind in source.columns)
    return (
        f"CREATE TABLE {source.table} (project TEXT NOT NULL, key TEXT NOT NULL, {columns}, "
        f"day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
        f"CREATE INDEX {source.table}_day ON {source.table} (day);\n"
    )


def _tables(*names: str) -> str:
    """The SQL that makes the tables of these sources."""
    by = {source.table: source for source in SOURCES}
    return "".join(_table(by[name]) for name in names)


FIRST = (
    "CREATE TABLE cursors (project TEXT NOT NULL, source TEXT NOT NULL, inode INTEGER, "
    "offset INTEGER, head TEXT, size INTEGER, mtime INTEGER, PRIMARY KEY (project, source)) "
    "WITHOUT ROWID;\n"
    "CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;\n"
    "CREATE TABLE builds (at TEXT NOT NULL, ms INTEGER, bytes INTEGER, rows INTEGER, "
    "left INTEGER);\n"
    + _tables(
        "events",
        "acts",
        "items",
        "transitions",
        "outbox",
        "ci_jobs",
        "merges",
        "questions",
        "queue",
        "merged",
        "ci_prs",
    )
    + "CREATE INDEX transitions_slug ON transitions (project, slug, to_status);\n"
    "CREATE INDEX ci_jobs_run ON ci_jobs (project, run, attempt);\n"
)

RECORDS = (
    _tables("brief_versions", "row_pulls", "runs", "spend_days", "spend_rows", "word_sends")
    + "CREATE INDEX brief_versions_slug ON brief_versions (project, slug, at);\n"
    "CREATE INDEX row_pulls_slug ON row_pulls (project, slug);\n"
    "CREATE INDEX runs_run ON runs (project, run, attempt);\n"
)
"""The records jbus keeps of what its snapshots overwrite (`jbus.history`, `jbus.spent`), and
`word-sends.json`."""

MIGRATIONS: tuple[str, ...] = (FIRST, RECORDS)
"""`MIGRATIONS[n]` takes a store from version `n` to `n + 1`. Append, never edit one."""

RED = "('failure', 'timed_out', 'startup_failure', 'action_required')"
GREEN = "('success', 'skipped', 'neutral')"
WEEK = "date({day}, '-6 days', 'weekday 0')"
"""The Sunday a local date's week starts on."""


def _quantiles(table: str, value: str) -> str:
    """The median and the 85th percentile of `value` over each week of `table`, of the values
    that are 0 or more: the median as `statistics.median`, the mean of the two middle values for
    an even count, and the 85th as the scorecard's `pct`, the value at index
    `min(n - 1, int(0.85 * n))` of the sorted values."""
    return (
        f"WITH ranked AS (SELECT week, {value} AS value, "
        f"row_number() OVER (PARTITION BY week ORDER BY {value}) AS place, "
        f"count(*) OVER (PARTITION BY week) AS n FROM {table} WHERE {value} >= 0) "
        "SELECT week, max(n) AS n, "
        "avg(CASE WHEN place IN ((n + 1) / 2, (n + 2) / 2) THEN value END) AS median, "
        "max(CASE WHEN place - 1 = min(n - 1, CAST(0.85 * n AS INTEGER)) THEN value END) AS p85, "
        "max(value) AS most FROM ranked GROUP BY week"
    )


VIEWS: tuple[tuple[str, str], ...] = (
    (
        "item_slugs",
        "SELECT project, item, slug FROM (SELECT project, item, slug, row_number() OVER "
        "(PARTITION BY project, item ORDER BY at, key) AS place FROM items "
        "WHERE slug IS NOT NULL) WHERE place = 1",
    ),
    (
        "row_goes",
        "SELECT i.project, coalesce(i.slug, s.slug) AS slug, min(i.at) AS approved FROM items i "
        "LEFT JOIN item_slugs s ON s.project = i.project AND s.item = i.item "
        "WHERE i.verb = 'approved' AND coalesce(i.slug, s.slug) IS NOT NULL GROUP BY 1, 2",
    ),
    (
        "row_moves",
        "SELECT project, slug, to_status, at, day FROM (SELECT project, slug, to_status, at, day, "
        "row_number() OVER (PARTITION BY project, slug, to_status ORDER BY at, key) AS place "
        "FROM transitions) WHERE place = 1",
    ),
    (
        "lead_times",
        "WITH rows AS (SELECT project, slug FROM transitions UNION SELECT project, slug FROM queue "
        "UNION SELECT project, slug FROM row_goes), "
        "ends AS (SELECT r.project, r.slug, coalesce(m.merged_at, t.at) AS merged_at, "
        "CASE WHEN m.merged_at IS NOT NULL THEN m.day ELSE t.day END AS day, "
        "coalesce(m.number, q.pr) AS pr, "
        "nullif(min(coalesce(g.approved, '~'), coalesce(q.approval_ran_at, '~'), "
        "coalesce(l.at, '~')), '~') AS go FROM rows r "
        "LEFT JOIN merged m ON m.project = r.project AND m.slug = r.slug "
        "LEFT JOIN row_moves t ON t.project = r.project AND t.slug = r.slug "
        "AND t.to_status = 'merged' "
        "LEFT JOIN row_moves l ON l.project = r.project AND l.slug = r.slug "
        "AND l.to_status = 'launched' "
        "LEFT JOIN queue q ON q.project = r.project AND q.slug = r.slug "
        "LEFT JOIN row_goes g ON g.project = r.project AND g.slug = r.slug) "
        "SELECT project, slug, pr, coalesce(go, merged_at) AS go, merged_at, day, "
        f"{WEEK.format(day='day')} AS week, "
        "round(max(0.0, (julianday(merged_at) - julianday(coalesce(go, merged_at))) * 1440.0), "
        "4) AS minutes FROM ends WHERE merged_at IS NOT NULL",
    ),
    (
        "main_runs",
        "WITH last AS (SELECT project, run, max(attempt) AS attempt FROM ci_jobs "
        "WHERE branch = 'main' AND event = 'push' GROUP BY project, run) "
        "SELECT j.project, j.run, j.attempt, max(j.sha) AS sha, max(j.pr) AS pr, "
        "min(j.created) AS created, max(j.completed) AS completed, min(j.day) AS day, "
        f"CASE WHEN sum(j.conclusion IN {RED}) > 0 THEN 'red' "
        f"WHEN sum(coalesce(j.conclusion, '') NOT IN {GREEN}) = 0 THEN 'green' "
        "ELSE 'pending' END AS state "
        "FROM ci_jobs j JOIN last ON last.project = j.project AND last.run = j.run "
        "AND last.attempt = j.attempt GROUP BY j.project, j.run, j.attempt",
    ),
    (
        "main_checks",
        "SELECT project, sha, pr, state, completed, first, day FROM (SELECT project, sha, pr, "
        "state, completed, min(created) OVER (PARTITION BY project, sha) AS first, "
        "min(day) OVER (PARTITION BY project, sha) AS day, row_number() OVER "
        "(PARTITION BY project, sha ORDER BY created DESC, run DESC) AS place FROM main_runs) "
        "WHERE place = 1",
    ),
    (
        "main_spells",
        "WITH judged AS (SELECT * FROM main_checks WHERE state IN ('red', 'green')), "
        "marked AS (SELECT *, CASE WHEN state = 'red' AND coalesce(lag(state) OVER "
        "(PARTITION BY project ORDER BY first, sha), 'green') = 'green' THEN 1 ELSE 0 END "
        "AS opens FROM judged), "
        "grouped AS (SELECT *, sum(opens) OVER (PARTITION BY project ORDER BY first, sha "
        "ROWS UNBOUNDED PRECEDING) AS spell FROM marked), "
        "ends AS (SELECT project, spell, completed AS green_at, sha AS end_sha, row_number() "
        "OVER (PARTITION BY project, spell ORDER BY first, sha) AS place FROM grouped "
        "WHERE state = 'green' AND spell > 0) "
        "SELECT g.project, g.spell, g.pr AS start_pr, g.sha AS start_sha, "
        "g.completed AS first_fail_at, g.day, "
        f"{WEEK.format(day='g.day')} AS week, e.end_sha, e.green_at, "
        "round((julianday(e.green_at) - julianday(g.completed)) * 1440.0, 1) "
        "AS minutes_to_green FROM grouped g "
        "LEFT JOIN ends e ON e.project = g.project AND e.spell = g.spell AND e.place = 1 "
        "WHERE g.opens = 1",
    ),
    (
        "change_failures",
        "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, l.week, EXISTS (SELECT 1 FROM "
        "main_spells s WHERE s.project = l.project AND s.start_pr = l.pr) AS opened_spell "
        "FROM lead_times l WHERE l.pr IS NOT NULL",
    ),
    ("weekly_lead_time", _quantiles("lead_times", "minutes")),
    (
        "weekly_change_failure",
        "SELECT week, sum(opened_spell) AS failures, count(*) AS merged, "
        "1.0 * sum(opened_spell) / count(*) AS rate FROM change_failures GROUP BY week",
    ),
    (
        "brief_at_launch",
        "SELECT t.project, t.slug, t.at AS launched_at, t.day, (SELECT v.sha FROM brief_versions v "
        "WHERE v.project = t.project AND v.slug = t.slug AND v.at <= t.at "
        "ORDER BY v.at DESC, v.key DESC LIMIT 1) AS sha, (SELECT count(*) FROM brief_versions v "
        "WHERE v.project = t.project AND v.slug = t.slug AND v.at > t.at AND v.sha != '') "
        "AS changed_after FROM transitions t WHERE t.to_status = 'launched'",
    ),
    (
        "run_attempts",
        "SELECT project, run, max(workflow) AS workflow, max(sha) AS sha, max(branch) AS branch, "
        "max(event) AS event, max(pr) AS pr, count(*) AS attempts, min(day) AS day, "
        f"min(CASE WHEN conclusion IN {RED} THEN updated END) AS first_fail_at, "
        f"min(CASE WHEN conclusion IN {RED} THEN attempt END) AS first_fail_attempt, "
        "max(updated) AS last_at, (SELECT r.conclusion FROM runs r WHERE r.project = runs.project "
        "AND r.run = runs.run ORDER BY r.attempt DESC LIMIT 1) AS last_conclusion "
        "FROM runs GROUP BY project, run",
    ),
    (
        "carried_words",
        "SELECT a.project, a.id AS word, a.at AS kept_at, a.said_at, a.said_in, a.source, "
        "a.party, a.route, a.subject, a.outcome, a.words_len, s.thread, s.sent_at, "
        "coalesce(s.waiting, 0) AS waiting, a.day FROM acts a LEFT JOIN word_sends s "
        "ON s.project = a.project AND s.word = a.id WHERE a.verb = 'word'",
    ),
    (
        "weekly_restore",
        "SELECT s.week, count(*) AS spells, q.median, q.most, "
        "sum(s.green_at IS NULL) AS still_open, sum(s.minutes_to_green < 0) AS negative "
        "FROM main_spells s LEFT JOIN ("
        + _quantiles("main_spells", "minutes_to_green")
        + ") q ON q.week = s.week GROUP BY s.week",
    ),
)
"""Each view by its name, in an order in which each reads only views made before it."""
