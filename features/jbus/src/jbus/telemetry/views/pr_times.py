"""Each pull request `ci-prs.jsonl` holds and `jmerge` logged as merged, in the week of its first
merge line from a minute before it opened on (a line is stamped to the minute), since `merge.log`
can hold an older repo's lines of the same number, as jstack's does from 2026-10-10 to 10-14. It has
its minutes from open to merge, and `first_round` where no check of the pull request failed and
`jmerge` never waited on a crew's fix round (`CREW_FIX`). `first_round` is None for a pull request
`ci.jsonl` kept no `pull_request` check of: whether one failed is not known, as for every one merged
from 2026-10-21 to 2026-10-25, among other days the ledger kept no checks of."""

from jbus.telemetry.schema import CREW_FIX, RED, WEEK

SQL = (
    "WITH merged_lines AS (SELECT c.project, c.number, min(m.day) AS day FROM ci_prs c "
    "JOIN merges m ON m.project = c.project AND m.number = c.number AND m.verb = 'merged' "
    "AND julianday(m.at) >= julianday(c.created) - 1 / 1440.0 GROUP BY c.project, c.number) "
    "SELECT c.project, c.number AS pr, c.created AS opened, c.merged AS merged_at, m.day, "
    f"{WEEK.format(day='m.day')} AS week, "
    "round((julianday(c.merged) - julianday(c.created)) * 1440.0, 4) AS minutes, "
    "CASE WHEN EXISTS (SELECT 1 FROM ci_jobs j WHERE j.project = c.project "
    "AND j.pr = c.number AND j.event = 'pull_request') THEN "
    "NOT EXISTS (SELECT 1 FROM ci_jobs j WHERE j.project = c.project AND j.pr = c.number "
    f"AND j.event = 'pull_request' AND j.conclusion IN {RED}) "
    "AND NOT EXISTS (SELECT 1 FROM merges w WHERE w.project = c.project "
    f"AND w.number = c.number AND w.verb = 'wait' AND w.label IN {CREW_FIX}) "
    "END AS first_round "
    "FROM ci_prs c JOIN merged_lines m ON m.project = c.project AND m.number = c.number "
    "WHERE c.merged IS NOT NULL AND c.created IS NOT NULL"
)
