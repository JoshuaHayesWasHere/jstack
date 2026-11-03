"""Each pull request `jmerge` merged, from the second it was ready, its required checks passed at
the head it merged at, to the second its merge began, in seconds and minutes, with the code that
held it longest (`blocker`) and the seconds of each (`blockers`, JSON).

It is `jmerge`'s own record (`how` `jmerge`, `merge-waits.jsonl`) where there is one. A merge with
none, as every one before the record began on 2026-11-03, is inferred from what the store keeps
(`how` `checks`): from the end of the last `pull_request` job that passed at the merged head, the
head `ci-prs.jsonl` keeps, to GitHub's merge time, which counts the merge call's own seconds too
and names no blocker. It reads `pr_times`, so it counts only merges `jmerge` logged."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT project, number AS pr, ready, at AS began, day, {WEEK.format(day='day')} AS week, "
    "'jmerge' AS how, seconds, round(seconds / 60.0, 4) AS minutes, blocker, blockers "
    "FROM merge_waits WHERE seconds IS NOT NULL AND number IS NOT NULL "
    "UNION ALL SELECT p.project, p.pr, r.ready, p.merged_at, p.day, p.week, 'checks', "
    "round((julianday(p.merged_at) - julianday(r.ready)) * 86400.0, 3), "
    "round((julianday(p.merged_at) - julianday(r.ready)) * 1440.0, 4), NULL, NULL "
    "FROM pr_times p JOIN ci_prs c ON c.project = p.project AND c.number = p.pr "
    "JOIN (SELECT project, sha, max(completed) AS ready FROM ci_jobs "
    "WHERE event = 'pull_request' AND conclusion = 'success' GROUP BY project, sha) r "
    "ON r.project = c.project AND r.sha = c.head "
    "WHERE NOT EXISTS (SELECT 1 FROM merge_waits w WHERE w.project = p.project "
    "AND w.number = p.pr)"
)
