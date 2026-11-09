"""Each week's typed messages of `ask_ledger` that are settled (S3), the lost ones among them, those
still waiting, and the rate, with no labels."""

SQL = (
    "SELECT project, week, sum(joined <> 'waiting') AS typed, sum(joined = 'unanswered') AS lost, "
    "sum(joined = 'waiting') AS waiting, "
    "1.0 * sum(joined = 'unanswered') / nullif(sum(joined <> 'waiting'), 0) AS rate "
    "FROM ask_ledger GROUP BY project, week"
)
