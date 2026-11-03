"""Each project with a row merged since the stall record began (`stalls_since`): the projects the
stall minutes count, since every project's pass keeps the record."""

SQL = "SELECT DISTINCT project FROM lead_times WHERE day >= (SELECT day FROM stalls_since)"
