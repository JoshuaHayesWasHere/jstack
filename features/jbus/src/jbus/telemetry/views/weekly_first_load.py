"""Each week from the first install record's on, and the crew first load of the latest install by
the week's end (`first_loads`), in KB of 1,000 bytes, with `installs`, how many installs the week
ran on: the one it began on and each new one in it."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"WITH RECURSIVE weeks (week) AS (SELECT min({WEEK.format(day='day')}) FROM first_loads "
    "UNION ALL SELECT date(week, '+7 days') FROM weeks "
    "WHERE date(week, '+7 days') <= date('now', '+1 day')) "
    "SELECT w.week, (SELECT f.bytes / 1000.0 FROM first_loads f "
    "WHERE f.day < date(w.week, '+7 days') ORDER BY f.at DESC, f.key DESC LIMIT 1) AS kb, "
    "(SELECT count(*) FROM first_loads f WHERE f.day >= w.week "
    "AND f.day < date(w.week, '+7 days')) "
    "+ EXISTS (SELECT 1 FROM first_loads f WHERE f.day < w.week) AS installs "
    "FROM weeks w WHERE w.week IS NOT NULL"
)
