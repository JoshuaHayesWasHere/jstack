"""Each week's change failure rate (S6): the rows of `change_failures` merged in it, and the share
of them that opened a spell."""

SQL = (
    "SELECT project, week, sum(opened_spell) AS failures, count(*) AS merged, "
    "1.0 * sum(opened_spell) / count(*) AS rate FROM change_failures GROUP BY project, week"
)
