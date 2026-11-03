"""Each week's reads of which instances are capped, of `capped_spells`, and the minutes they hold
every instance capped."""

SQL = (
    "SELECT week, count(*) AS reads, sum(minutes) AS minutes FROM capped_spells "
    "WHERE day IS NOT NULL GROUP BY week"
)
