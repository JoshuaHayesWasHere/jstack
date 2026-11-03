"""Each project's last line of each day `jgauge spend` counted (`spend_days`)."""

SQL = (
    "SELECT project, spent_on, units, sends, homes, capped FROM (SELECT *, row_number() "
    "OVER (PARTITION BY project, spent_on ORDER BY at DESC, key DESC) AS place "
    "FROM spend_days WHERE spent_on IS NOT NULL) WHERE place = 1"
)
