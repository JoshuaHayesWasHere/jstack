"""Each week's typed messages of `ask_ledger`, and those among them whose `asks` is `needs`, that
ask what needs the user (`jbus.telemetry.asks`). A message is counted the week it was typed,
waiting or not."""

SQL = "SELECT week, count(*) AS typed, sum(asks IS 'needs') AS asks FROM ask_ledger GROUP BY week"
