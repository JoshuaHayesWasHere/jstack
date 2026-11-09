"""Each week's rows merged, of `lead_times`."""

SQL = "SELECT project, week, count(*) AS merged FROM lead_times GROUP BY project, week"
