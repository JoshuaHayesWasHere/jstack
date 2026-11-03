"""Each week's red spells of main (S7), by the week each opened: the median and the most minutes to
green, how many are still open, and how many have negative minutes."""

from jbus.telemetry.schema import quantiles

SQL = (
    "SELECT s.week, count(*) AS spells, q.median, q.most, "
    "sum(s.green_at IS NULL) AS still_open, sum(s.minutes_to_green < 0) AS negative "
    "FROM main_spells s LEFT JOIN ("
    + quantiles("main_spells", "minutes_to_green")
    + ") q ON q.week = s.week GROUP BY s.week"
)
