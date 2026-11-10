"""Each reviewer thread, one row per launch: its pull request when one was open at launch, and the
state then of `check`, the workflow at its head, so how many reviews launched on a passed head,
and the lag from push to launch, is one query.

A reviewer thread is a thread of role `reviewer` (`call_rows`), launched at its first call and
ended at its last; `tokens` is input, cache writes, cache reads and output, summed over its calls.
`pr` is the pull request of the thread's slug open at launch (`ci_prs`): one on a branch named
for the slug, or one jbus linked to the row (`row_pulls`), whose branch can differ. A review
launched before its pull request opened, as a row's first review is since #1169, has none, and no
check state: `check` runs on a pull request's pushes, not a bare branch's. `pr` is none too where
`ci-prs.jsonl` holds no pull request of the project, which is every project but those `jbus ci`
keeps.

`head` is the head jbus recorded the thread was launched at (`review_heads`, which
`jbus.reviewlaunch` writes), and none where no record names the thread, as for a thread launched
before jbus kept the record. `number` is its seat, `#<n>`, as the record gives it. The `check`
run of the pull request's branch at that sha says how it stood: `pushed` is when the run was
created, the push, and `lag_minutes` the minutes from it to launch, none where the run was created
after. `check_state` is the run's conclusion where it ended by launch, `running` where it had
started and not ended, and `queued` where it had not started, as a review asked the moment a head
is pushed is. The run is the newest attempt started by launch, or else the first to start. A run
is matched on its branch, not its `pr`, which GitHub leaves out of some `pull_request` runs.
`check_state` is none where the store has no such run.

`again` is how many reviewer threads of the slug, at the same seat, launched before this one at
the same `head`, so a launch at a head a reviewer of that seat had already been launched at is
one where `again > 0`. It is 0 where `head` is none: a launch with no head on record is no repeat
of another, whose head is unknown too.

The threads are read from `calls` first, a `CROSS JOIN` fixing the order: the store keeps no
statistics, and SQLite would otherwise read every call of a provider for each reviewer session,
which takes half a minute on a store of a quarter of a million calls."""

SQL = (
    "WITH threads AS (SELECT s.project, s.thread, s.slug, min(c.at) AS launched, "
    "max(c.at) AS ended, sum(c.input + c.cache_write + c.cache_read + c.output) AS tokens, "
    "sum(c.output) AS output FROM calls c CROSS JOIN sessions s ON s.provider = c.provider "
    "AND s.session = c.session WHERE s.role = 'reviewer' GROUP BY s.project, s.thread, s.slug), "
    "links AS (SELECT project, slug, number FROM row_pulls "
    "UNION SELECT project, branch, number FROM ci_prs), "
    "opened AS (SELECT t.project, t.thread, p.number, p.branch, p.created, row_number() "
    "OVER (PARTITION BY t.project, t.thread ORDER BY p.created DESC) AS newest "
    "FROM threads t JOIN links l ON l.project = t.project AND l.slug = t.slug "
    "JOIN ci_prs p ON p.project = l.project AND p.number = l.number "
    "WHERE julianday(p.created) <= julianday(t.launched) "
    "AND (p.closed IS NULL OR julianday(p.closed) > julianday(t.launched))), "
    "headed AS (SELECT t.project, t.thread, h.head AS sha, h.number AS seat "
    "FROM threads t JOIN review_heads h ON h.project = t.project AND h.thread = t.thread "
    "WHERE h.head IS NOT NULL), "
    "checked AS (SELECT h.project, h.thread, r.created, r.started, r.updated, r.conclusion, "
    "row_number() OVER (PARTITION BY h.project, h.thread "
    "ORDER BY julianday(r.started) <= julianday(t.launched) DESC, "
    "CASE WHEN julianday(r.started) <= julianday(t.launched) THEN -julianday(r.started) "
    "ELSE julianday(r.started) END, r.attempt DESC) AS newest "
    "FROM headed h JOIN threads t ON t.project = h.project AND t.thread = h.thread "
    "JOIN opened o ON o.project = h.project AND o.thread = h.thread AND o.newest = 1 "
    "JOIN runs r ON r.project = h.project AND r.branch = o.branch AND r.sha = h.sha "
    "WHERE r.workflow = 'check' AND r.event = 'pull_request') "
    "SELECT t.project, t.slug, t.thread, o.number AS pr, t.launched, t.ended, t.tokens, "
    "t.output, h.sha AS head, h.seat AS number, "
    "CASE WHEN julianday(k.created) <= julianday(t.launched) THEN k.created END AS pushed, "
    "CASE WHEN k.started IS NULL THEN NULL "
    "WHEN julianday(k.started) > julianday(t.launched) THEN 'queued' "
    "WHEN julianday(k.updated) <= julianday(t.launched) THEN k.conclusion ELSE 'running' END "
    "AS check_state, CASE WHEN julianday(k.created) <= julianday(t.launched) THEN "
    "round((julianday(t.launched) - julianday(k.created)) * 1440.0, 2) END AS lag_minutes, "
    "CASE WHEN h.sha IS NULL THEN 0 ELSE count(*) OVER (PARTITION BY t.project, t.slug, h.sha, "
    "h.seat ORDER BY t.launched, t.thread ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) "
    "END AS again FROM threads t "
    "LEFT JOIN opened o ON o.project = t.project AND o.thread = t.thread AND o.newest = 1 "
    "LEFT JOIN headed h ON h.project = t.project AND h.thread = t.thread "
    "LEFT JOIN checked k ON k.project = t.project AND k.thread = t.thread AND k.newest = 1"
)
