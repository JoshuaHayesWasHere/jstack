"""What each queued row came of: the session that last queued it (`queue.queued_by_session`, the
session of the last `jbus queue add` of its slug) and that session's role and thread, the row's
first brief version (`briefed`), the last message of role `user` in that thread before it
(`message`, as `<thread>/<message id>`, its `message_at`, and `created_by`, which tells the user's
typed words from an agent's), the row's own `approval_message`, and the `minutes` from that
message to the first brief version. A row queued by no session (jbus's pass, a Codex home) is
left out, and a thread with no such message, or a session the store has no transcript of, keeps
NULL there."""

SQL = (
    "WITH briefs AS (SELECT project, slug, min(at) AS briefed FROM brief_versions "
    "GROUP BY project, slug), "
    "queued AS (SELECT q.project, q.slug, q.queued_by_session AS session, s.role AS "
    "queued_by_role, s.thread, b.briefed, q.approval_message FROM queue q "
    "LEFT JOIN sessions s ON s.session = q.queued_by_session "
    "LEFT JOIN briefs b ON b.project = q.project AND b.slug = q.slug "
    "WHERE coalesce(q.queued_by_session, '') <> ''), "
    "said AS (SELECT q.project, q.slug, m.thread || '/' || m.id AS message, m.at AS message_at, "
    "m.created_by, row_number() OVER (PARTITION BY q.project, q.slug ORDER BY m.at DESC, m.key "
    "DESC) AS place FROM queued q JOIN messages m ON m.thread = q.thread AND m.role = 'user' "
    "AND m.at < q.briefed) "
    "SELECT q.project, q.slug, q.session, q.queued_by_role, q.thread, q.briefed, s.message, "
    "s.message_at, s.created_by, q.approval_message, "
    "round((julianday(q.briefed) - julianday(s.message_at)) * 1440.0, 4) AS minutes FROM queued q "
    "LEFT JOIN said s ON s.project = q.project AND s.slug = q.slug AND s.place = 1"
)
