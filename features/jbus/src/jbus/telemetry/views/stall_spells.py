"""Each spell a running row's thread was quiet or hung that a pass saw end (`stalls.jsonl`), with
its minutes, in the week of that pass: a spell runs from the thread's last write to its next
write, or to the pass that saw it wait on the user, end or go."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT project, slug, role, minutes, day, {WEEK.format(day='day')} AS week FROM stalls "
    "WHERE minutes IS NOT NULL AND day IS NOT NULL"
)
