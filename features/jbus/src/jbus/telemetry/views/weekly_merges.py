"""Each week's rows merged, of `lead_times`."""

SQL = "SELECT week, count(*) AS merged FROM lead_times GROUP BY week"
