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
- `ask_ledger`: each message the user typed (`TYPED`), a word said through the bots' chat or the
  view among them, and what followed it, the first of: a `row`, an act that cites the message by
  id (a word by its own id) and names a row; an `answer`, an act that cites it and answers a
  gate; a `reply`, the assistant's first message in its thread within `WAIT` minutes. An act
  counts whenever it came, since it names the message; a reply is only matched by time. With
  none, it is `waiting` until `WAIT` minutes have passed by the last build, then `unanswered`: a
  lost ask.
- `weekly_lost_asks` (S3): each week's typed messages that are settled, the lost ones among
  them, those still waiting, and the rate, with no labels.
- `pr_times`: each pull request `ci-prs.jsonl` holds and `jmerge` logged as merged, in the week
  of its merge line, with its minutes from open to merge, and `first_round` where no check of
  the pull request failed and `jmerge` never waited on a crew's fix round (`CREW_FIX`).
- `weekly_pr_to_merge`, `weekly_first_round`, `weekly_merges` and `weekly_doors`: each week's
  open-to-merge median, share merged in the first round, rows merged, and door acts done, with
  `not_yours` those a home, a bot or jbus did and the user did not, save one done on a message
  the user typed, as the home does on `--message`, which is the user's.
- `call_rows`: each agent call with its session's thread, project, role and slug, and
  its spend in `jgauge spend`'s units (`UNITS`).
- `row_spend`: each merged row's spend by the role and the provider of the threads that spent
  it: calls, the four counts and units.
"""

from __future__ import annotations

from jbus.telemetry import messages
from jbus.telemetry.records import SOURCES, Source
from jgauge import spend


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
    "CREATE TABLE cursors (project TEXT NOT NULL, source TEXT NOT NULL, inode INTEGER, offset "
    "INTEGER, head TEXT, size INTEGER, mtime INTEGER, PRIMARY KEY (project, source)) WITHOUT "
    "ROWID;\n"
    "CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;\n"
    "CREATE TABLE builds (at TEXT NOT NULL, ms INTEGER, bytes INTEGER, rows INTEGER, left "
    "INTEGER);\n"
    "CREATE TABLE events (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, event TEXT, slug "
    "TEXT, loud TEXT, item TEXT, act TEXT, subject TEXT, line_len INTEGER, text_len INTEGER, "
    "day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX events_day ON events (day);\n"
    "CREATE TABLE acts (project TEXT NOT NULL, key TEXT NOT NULL, id TEXT, at TEXT, verb TEXT, "
    "subject TEXT, outcome TEXT, party TEXT, party_name TEXT, route TEXT, source TEXT, ref "
    "TEXT, said_in TEXT, said_at TEXT, gate INTEGER, doors INTEGER, picks INTEGER, words_len "
    "INTEGER, line_len INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX acts_day ON acts (day);\n"
    "CREATE TABLE items (project TEXT NOT NULL, key TEXT NOT NULL, id TEXT, at TEXT, item TEXT,"
    " verb TEXT, slug TEXT, by TEXT, by_user TEXT, place TEXT, title_len INTEGER, line_len "
    "INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX items_day ON items (day);\n"
    "CREATE TABLE transitions (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, slug TEXT, "
    "from_status TEXT, to_status TEXT, by TEXT, why_len INTEGER, day TEXT, PRIMARY KEY "
    "(project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX transitions_day ON transitions (day);\n"
    "CREATE TABLE outbox (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, thread TEXT, row "
    "TEXT, template TEXT, needs TEXT, send_key TEXT, went TEXT, rule TEXT, day TEXT, PRIMARY "
    "KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX outbox_day ON outbox (day);\n"
    "CREATE TABLE ci_jobs (project TEXT NOT NULL, key TEXT NOT NULL, run INTEGER, job INTEGER, "
    "attempt INTEGER, name TEXT, sha TEXT, branch TEXT, pr INTEGER, event TEXT, created TEXT, "
    "started TEXT, completed TEXT, conclusion TEXT, runner TEXT, kind TEXT, steps INTEGER, "
    "selection TEXT, slowest_s REAL, tail_s REAL, workers INTEGER, tests INTEGER, signs "
    "INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX ci_jobs_day ON ci_jobs (day);\n"
    "CREATE TABLE merges (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, verb TEXT, number "
    "INTEGER, slug TEXT, label TEXT, line_len INTEGER, day TEXT, PRIMARY KEY (project, key)) "
    "WITHOUT ROWID;\n"
    "CREATE INDEX merges_day ON merges (day);\n"
    "CREATE TABLE questions (project TEXT NOT NULL, key TEXT NOT NULL, number INTEGER, slug "
    "TEXT, thread TEXT, asked_at TEXT, holds INTEGER, options INTEGER, answered_at TEXT, "
    "answered_by TEXT, closed_by TEXT, answer_place TEXT, keeps INTEGER, ref TEXT, question_len"
    " INTEGER, default_len INTEGER, context_len INTEGER, words_len INTEGER, day TEXT, PRIMARY "
    "KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX questions_day ON questions (day);\n"
    "CREATE TABLE queue (project TEXT NOT NULL, key TEXT NOT NULL, slug TEXT, status TEXT, item"
    " TEXT, entry TEXT, priority INTEGER, thread TEXT, pr INTEGER, on_hold INTEGER, role TEXT, "
    "updated TEXT, approval_basis TEXT, approval_ref TEXT, approval_said_at TEXT, "
    "approval_ran_at TEXT, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX queue_day ON queue (day);\n"
    "CREATE TABLE merged (project TEXT NOT NULL, key TEXT NOT NULL, slug TEXT, number INTEGER, "
    "merged_at TEXT, merge_commit TEXT, state TEXT, title_len INTEGER, day TEXT, PRIMARY KEY "
    "(project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX merged_day ON merged (day);\n"
    "CREATE TABLE ci_prs (project TEXT NOT NULL, key TEXT NOT NULL, number INTEGER, branch "
    "TEXT, head TEXT, created TEXT, updated TEXT, merged TEXT, closed TEXT, merge_commit TEXT, "
    "pushes INTEGER, day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX ci_prs_day ON ci_prs (day);\n"
    "CREATE INDEX transitions_slug ON transitions (project, slug, to_status);\n"
    "CREATE INDEX ci_jobs_run ON ci_jobs (project, run, attempt);\n"
)
"""The store at version 1, as it was made, written out: a column a source gains later is a
migration of its own, and never an edit of this one."""

RECORDS = (
    _tables("brief_versions", "row_pulls", "runs", "spend_days", "spend_rows", "word_sends")
    + "CREATE INDEX brief_versions_slug ON brief_versions (project, slug, at);\n"
    "CREATE INDEX row_pulls_slug ON row_pulls (project, slug);\n"
    "CREATE INDEX runs_run ON runs (project, run, attempt);\n"
)
"""The records jbus keeps of what its snapshots overwrite (`jbus.history`, `jbus.spent`), and
`word-sends.json`."""

PASSES = (
    "ALTER TABLE acts ADD COLUMN checked INTEGER;\n"
    "CREATE TABLE passes (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, seconds REAL, "
    "day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    "CREATE INDEX passes_at ON passes (at);\n"
)
"""Whether jbus read an act's words in T3 Code itself (`party.Evidence.checked`), and each pass's
seconds, the machine's, under the project `''`. An act a store read before this has no `checked`."""

MESSAGES = messages.TABLE_SQL + "CREATE INDEX acts_ref ON acts (ref);\n"
"""The messages of T3 Code's threads (`jbus.telemetry.messages`), and the index by which an act
finds the message it cites."""

TOKENS = (
    "CREATE TABLE sessions (provider TEXT NOT NULL, session TEXT NOT NULL, thread TEXT, "
    "instance TEXT, project TEXT, role TEXT, slug TEXT, PRIMARY KEY (provider, session)) "
    "WITHOUT ROWID;\n"
    "CREATE INDEX sessions_row ON sessions (project, slug);\n"
    "CREATE TABLE calls (provider TEXT NOT NULL, call TEXT NOT NULL, session TEXT NOT NULL, "
    "agent TEXT, at TEXT, model TEXT, input INTEGER NOT NULL, cache_write INTEGER NOT NULL, "
    "cache_read INTEGER NOT NULL, output INTEGER NOT NULL, final INTEGER NOT NULL, day TEXT, "
    "PRIMARY KEY (provider, call)) WITHOUT ROWID;\n"
    "CREATE INDEX calls_session ON calls (provider, session);\n"
    "CREATE INDEX calls_day ON calls (day);\n"
)
"""Each agent call's token usage, and the thread of each session (`tokens`)."""

MIGRATIONS: tuple[str, ...] = (FIRST, RECORDS, PASSES, MESSAGES, TOKENS)
"""`MIGRATIONS[n]` takes a store from version `n` to `n + 1`. Append, never edit one."""

UNITS = (
    f"(c.input * {spend.PLAIN!r} + c.cache_write * {spend.WRITTEN!r} "
    f"+ c.cache_read * {spend.CACHED!r} + c.output * {spend.OUTPUT!r}) "
    f"* (CASE WHEN instr(c.model, '{spend.OPUS_NAME}') > 0 THEN {spend.OPUS!r} ELSE 1 END)"
)
"""A call's spend in `jgauge spend`'s units, built from `jgauge.spend`'s rates as
`jgauge.spend.units` weighs a run: `c.input` is the uncached input, and Opus goes by the call's
own model. `instr` matches case and all, as Python's `in` does, where `LIKE` would not."""
RED = "('failure', 'timed_out', 'startup_failure', 'action_required')"
GREEN = "('success', 'skipped', 'neutral')"
WEEK = "date({day}, '-6 days', 'weekday 0')"
"""The Sunday a local date's week starts on."""
WAIT = 120
"""The minutes a typed message waits for a reply before it is a lost ask: in the audit week
(2026-10-25 to 10-31) each of the user's 603 messages had its first reply within 2 hours, 597
within 5 minutes."""
TYPED = (
    "role = 'user' AND created_by = 'user' AND id NOT LIKE 'limit-resume:%' AND kind <> 'dropped'"
)
"""A message the user typed: T3 Code's `createdBy` is the user, it is not T3 Code's resume after
a usage limit, and its text is not one T3 Code or an agent put in the user's turn."""
CREW_FIX = (
    "('no-fixed', 'fix-unreviewed', 'content-changed', 'dropped', 'scoped-unruled', "
    "'unruled-drops', 'declines-unruled')"
)
"""The labels of `merge.log`'s waits on a crew's fix round: findings not handled, a fix not
reviewed, content changed after its review, and drops a rebase made and no one ruled on."""


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
        "call_rows",
        "SELECT c.provider, c.call, c.session, c.agent, c.at, c.day, c.model, c.input, "
        "c.cache_write, c.cache_read, c.output, c.final, s.thread, s.instance, s.project, "
        "s.role, s.slug, "
        f"{UNITS} AS units FROM calls c "
        "LEFT JOIN sessions s ON s.provider = c.provider AND s.session = c.session",
    ),
    (
        "row_spend",
        "SELECT l.project, l.slug, l.pr, l.merged_at, l.day, l.week, c.role, c.provider, "
        "count(*) AS calls, sum(c.input) AS input, sum(c.cache_write) AS cache_write, "
        "sum(c.cache_read) AS cache_read, sum(c.output) AS output, sum(c.units) AS units "
        "FROM lead_times l JOIN call_rows c ON c.project = l.project AND c.slug = l.slug "
        "GROUP BY l.project, l.slug, c.role, c.provider",
    ),
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
        "pr_times",
        "WITH merged_lines AS (SELECT project, number, min(day) AS day FROM merges "
        "WHERE verb = 'merged' AND number IS NOT NULL GROUP BY project, number) "
        "SELECT c.project, c.number AS pr, c.created AS opened, c.merged AS merged_at, m.day, "
        f"{WEEK.format(day='m.day')} AS week, "
        "round((julianday(c.merged) - julianday(c.created)) * 1440.0, 4) AS minutes, "
        "NOT EXISTS (SELECT 1 FROM ci_jobs j WHERE j.project = c.project AND j.pr = c.number "
        f"AND j.event = 'pull_request' AND j.conclusion IN {RED}) "
        "AND NOT EXISTS (SELECT 1 FROM merges w WHERE w.project = c.project "
        f"AND w.number = c.number AND w.verb = 'wait' AND w.label IN {CREW_FIX}) AS first_round "
        "FROM ci_prs c JOIN merged_lines m ON m.project = c.project AND m.number = c.number "
        "WHERE c.merged IS NOT NULL AND c.created IS NOT NULL",
    ),
    ("weekly_pr_to_merge", _quantiles("pr_times", "minutes")),
    (
        "weekly_first_round",
        "SELECT week, count(*) AS n, sum(first_round) AS first_round, "
        "100.0 * sum(first_round) / count(*) AS share FROM pr_times GROUP BY week",
    ),
    ("weekly_merges", "SELECT week, count(*) AS merged FROM lead_times GROUP BY week"),
    (
        "weekly_doors",
        f"SELECT {WEEK.format(day='a.day')} AS week, count(*) AS done, "
        "sum(coalesce(a.party, '') != 'user' AND NOT EXISTS (SELECT 1 FROM messages t "
        f"WHERE t.project = a.project AND {TYPED} AND a.ref = CASE WHEN "
        f"t.key = '{messages.WORD}' || t.id THEN t.id ELSE t.thread || '/' || t.id END)) "
        "AS not_yours FROM acts a "
        "WHERE a.doors > 0 AND a.outcome = 'done' AND a.day IS NOT NULL GROUP BY 1",
    ),
    (
        "pass_times",
        f"SELECT {WEEK.format(day='day')} AS week, seconds FROM passes "
        "WHERE day IS NOT NULL AND seconds IS NOT NULL",
    ),
    ("weekly_pass_time", _quantiles("pass_times", "seconds")),
    (
        "weekly_restore",
        "SELECT s.week, count(*) AS spells, q.median, q.most, "
        "sum(s.green_at IS NULL) AS still_open, sum(s.minutes_to_green < 0) AS negative "
        "FROM main_spells s LEFT JOIN ("
        + _quantiles("main_spells", "minutes_to_green")
        + ") q ON q.week = s.week GROUP BY s.week",
    ),
    (
        "ask_ledger",
        f"WITH typed AS (SELECT * FROM messages WHERE {TYPED}), "
        "links AS (SELECT t.project, t.key, CASE WHEN a.gate IS NOT NULL OR a.verb = 'answer' "
        "THEN 'answer' ELSE 'row' END AS joined, a.at AS joined_at, a.id AS link FROM typed t "
        f"JOIN acts a ON a.ref = CASE WHEN t.key = '{messages.WORD}' || t.id THEN t.id "
        "ELSE t.thread || '/' || t.id END "
        "WHERE a.gate IS NOT NULL OR a.verb = 'answer' OR a.subject IS NOT NULL "
        "UNION ALL SELECT t.project, t.key, 'reply', r.at, r.id FROM typed t JOIN messages r "
        "ON r.thread = t.thread AND r.role = 'assistant' AND r.at > t.at "
        f"AND julianday(r.at) <= julianday(t.at) + {WAIT} / 1440.0), "
        "ranked AS (SELECT *, row_number() OVER (PARTITION BY project, key ORDER BY "
        "CASE joined WHEN 'row' THEN 1 WHEN 'answer' THEN 2 ELSE 3 END, joined_at) AS place "
        "FROM links) "
        "SELECT t.project, t.id, t.thread, t.at, t.day, "
        f"{WEEK.format(day='t.day')} AS week, t.kind, coalesce(k.joined, CASE WHEN "
        "julianday((SELECT max(at) FROM builds)) - julianday(t.at) >= "
        f"{WAIT} / 1440.0 THEN 'unanswered' ELSE 'waiting' END) AS joined, k.joined_at, k.link, "
        "round((julianday(k.joined_at) - julianday(t.at)) * 1440.0, 1) AS minutes "
        "FROM typed t LEFT JOIN ranked k ON k.project = t.project AND k.key = t.key "
        "AND k.place = 1",
    ),
    (
        "weekly_lost_asks",
        "SELECT week, sum(joined <> 'waiting') AS typed, sum(joined = 'unanswered') AS lost, "
        "sum(joined = 'waiting') AS waiting, "
        "1.0 * sum(joined = 'unanswered') / nullif(sum(joined <> 'waiting'), 0) AS rate "
        "FROM ask_ledger GROUP BY week",
    ),
    (
        "weekly_typed_per_row",
        "WITH typed AS (SELECT week, count(*) AS typed FROM ask_ledger WHERE kind <> 'resume' "
        "GROUP BY week) SELECT m.week, coalesce(t.typed, 0) AS typed, m.merged, "
        "1.0 * coalesce(t.typed, 0) / m.merged AS per_row FROM weekly_merges m "
        "LEFT JOIN typed t ON t.week = m.week",
    ),
)
"""Each view by its name, in an order in which each reads only views made before it."""
