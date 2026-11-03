"""The first day `merge.log` has a wait labelled as a crew's fix round, the day `pr_times`'s
`first_round` can first tell a fix round with no red check from a first round."""

from jbus.telemetry.schema import CREW_FIX

SQL = f"SELECT min(day) AS day FROM merges WHERE verb = 'wait' AND label IN {CREW_FIX}"
