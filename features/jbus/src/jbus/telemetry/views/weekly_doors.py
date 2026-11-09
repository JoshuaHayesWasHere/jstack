"""Each week's door acts done, with `not_yours` those a home, a bot or jbus did and the user did
not, save one done on a message the user typed, as the home does on `--message`, which is the
user's."""

from jbus.telemetry import messages
from jbus.telemetry.schema import TYPED, WEEK

SQL = (
    f"SELECT a.project, {WEEK.format(day='a.day')} AS week, count(*) AS done, "
    "sum(coalesce(a.party, '') != 'user' AND NOT EXISTS (SELECT 1 FROM messages t "
    f"WHERE t.project = a.project AND {TYPED} AND a.ref = CASE WHEN "
    f"t.key = '{messages.WORD}' || t.id THEN t.id ELSE t.thread || '/' || t.id END)) "
    "AS not_yours FROM acts a "
    "WHERE a.doors > 0 AND a.outcome = 'done' AND a.day IS NOT NULL GROUP BY 1, 2"
)
