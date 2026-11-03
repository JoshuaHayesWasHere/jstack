"""Each week's share of pull requests merged in the first round, of those of `pr_times` whose checks
were kept."""

SQL = (
    "SELECT week, count(first_round) AS n, sum(first_round) AS first_round, "
    "100.0 * sum(first_round) / nullif(count(first_round), 0) AS share FROM pr_times "
    "GROUP BY week"
)
