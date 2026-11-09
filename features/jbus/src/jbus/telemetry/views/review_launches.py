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

`head` is the sha of the newest `check` run of the pull request's branch, since it opened, that
had started by launch; `pushed` is when that run was created, the push, and `lag_minutes` the
minutes from it to launch. `check_state` is that run's conclusion where it ended by launch, and
`running` where it ended after. A run is matched on its branch, not its `pr`, which GitHub leaves
out of some `pull_request` runs. A rerun counts from when it started, so one started after the
launch leaves the state at launch the earlier attempt's. `check_state` is none for a pull request
with no such run in the store.

`again` is how many reviewer threads of the slug launched before this one at the same `head`, so
a launch at a head a reviewer had already judged is one where `again > 0`. It is 0 where `head` is
none: a launch with no head on record, such as one before its pull request opened, is no repeat of
another, whose head is unknown too.

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
    "headed AS (SELECT o.project, o.thread, r.sha, r.created, r.updated, r.conclusion, "
    "row_number() OVER (PARTITION BY o.project, o.thread "
    "ORDER BY julianday(r.started) DESC, r.attempt DESC) AS newest "
    "FROM opened o JOIN threads t ON t.project = o.project AND t.thread = o.thread "
    "JOIN runs r ON r.project = o.project AND r.branch = o.branch "
    "WHERE o.newest = 1 AND r.workflow = 'check' AND r.event = 'pull_request' "
    "AND julianday(r.created) >= julianday(o.created) "
    "AND julianday(r.started) <= julianday(t.launched)) "
    "SELECT t.project, t.slug, t.thread, o.number AS pr, t.launched, t.ended, t.tokens, "
    "t.output, h.sha AS head, h.created AS pushed, CASE WHEN h.sha IS NULL THEN NULL "
    "WHEN julianday(h.updated) <= julianday(t.launched) THEN h.conclusion ELSE 'running' END "
    "AS check_state, round((julianday(t.launched) - julianday(h.created)) * 1440.0, 2) "
    "AS lag_minutes, CASE WHEN h.sha IS NULL THEN 0 ELSE count(*) OVER (PARTITION BY t.project, "
    "t.slug, h.sha ORDER BY t.launched, t.thread ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) "
    "END AS again FROM threads t "
    "LEFT JOIN opened o ON o.project = t.project AND o.thread = t.thread AND o.newest = 1 "
    "LEFT JOIN headed h ON h.project = t.project AND h.thread = t.thread AND h.newest = 1"
)
