"""How each brief version's last Result ended its row with no merge (`jbus.outcome.kind`):
`carried`, `nothing to change` or `dropped`. A line of `brief-versions.jsonl` written before
`history.brief` wrote it keeps none, and `row_outcomes` names the end of such a row by the rule it
had before."""

SQL = "ALTER TABLE brief_versions ADD COLUMN outcome TEXT;\n"
