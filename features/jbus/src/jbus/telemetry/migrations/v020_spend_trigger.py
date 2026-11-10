"""What woke the runs of each line of `spend-rows.jsonl` (`jgauge.spend.day_lines`): the send
key, whether the row's first prereview came before them that day, and their dollars. A line kept
before `jbus.spent` wrote them holds none, so its `trigger` is NULL, read as unknown."""

SQL = (
    "ALTER TABLE spend_rows ADD COLUMN trigger TEXT;\n"
    "ALTER TABLE spend_rows ADD COLUMN reviewed INTEGER;\n"
    "ALTER TABLE spend_rows ADD COLUMN dollars REAL;\n"
)
