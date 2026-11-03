"""Each week's merged rows of `row_words` (S1), and the share of them that are quiet: no message
names them."""

SQL = (
    "SELECT week, count(*) AS merged, sum(words = 0) AS quiet, "
    "100.0 * sum(words = 0) / count(*) AS share FROM row_words GROUP BY week"
)
