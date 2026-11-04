"""The first day of the stall record (`stalls.jsonl`): the day of its `began` line, which the first
pass that ran `jbus.stall.spells` wrote, or of its first spell where the file began before that line
was kept. A merged row before it is a gap of the stall minutes (`stall_gaps`), not a row with none,
and one from it on with no spell had none."""

SQL = "SELECT min(day) AS day FROM stalls"
