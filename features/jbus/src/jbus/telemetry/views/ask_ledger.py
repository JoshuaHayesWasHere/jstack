"""Each message the user typed (`jbus.telemetry.schema.TYPED`), a word said through the bots' chat
or the view among them, and what followed it, the first of: a `row`, an act that cites the message
by id (a word by its own id) and names a row; an `answer`, an act that cites it and answers a gate;
a `reply`, the assistant's first message in its thread within `WAIT` minutes. An act counts whenever
it came, since it names the message; a reply is only matched by time. With none, it is `waiting`
until `WAIT` minutes have passed by the last build, then `unanswered`: a lost ask."""

from jbus.telemetry import messages
from jbus.telemetry.schema import TYPED, WAIT, WEEK

SQL = (
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
    f"{WEEK.format(day='t.day')} AS week, t.kind, t.asks, coalesce(k.joined, CASE WHEN "
    "julianday((SELECT max(at) FROM builds)) - julianday(t.at) >= "
    f"{WAIT} / 1440.0 THEN 'unanswered' ELSE 'waiting' END) AS joined, k.joined_at, k.link, "
    "round((julianday(k.joined_at) - julianday(t.at)) * 1440.0, 1) AS minutes "
    "FROM typed t LEFT JOIN ranked k ON k.project = t.project AND k.key = t.key "
    "AND k.place = 1"
)
