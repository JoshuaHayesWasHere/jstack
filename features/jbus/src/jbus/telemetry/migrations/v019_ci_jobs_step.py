"""The step each failed job of `ci.jsonl` failed at (`jbus.ci.collect.failed_step`), which
`pr-checks-failed` classes a failed run by. The cursors of `ci_jobs` go, so the next build reads
each `ci.jsonl` again and fills `step` for the jobs the store already holds."""

SQL = (
    "ALTER TABLE ci_jobs ADD COLUMN step TEXT;\n"
    "DELETE FROM cursors WHERE source = 'ci_jobs';\n"
)
