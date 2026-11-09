"""Each week's reads of which instances are capped, of `capped_any_spells`: the minutes they hold
one instance or more capped, and their `share`, in percent, of the minutes the reads hold.

`weekly_capped` counts the minutes every instance was capped, and stays at 0 while one account is
free; this counts the minutes one was capped, while launches ran on the other.
"""

SQL = (
    "SELECT project, week, count(*) AS reads, sum(minutes) AS minutes, "
    "round(100.0 * sum(minutes) / nullif(sum(held), 0), 1) AS share FROM capped_any_spells "
    "WHERE day IS NOT NULL GROUP BY project, week"
)
