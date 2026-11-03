"""The first day of the stall record (`stalls.jsonl`), before which a merged row's quiet spells
were not kept: such a row is a gap of the stall minutes (`stall_gaps`), not a row with none."""

SQL = "SELECT min(day) AS day FROM stalls"
